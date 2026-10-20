from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from molt.matching import classify, match_text, to_opportunity
from molt.repository import list_items
from molt.source import save_release


def test_integral_contract_finds_equipment_only_in_tdr(release):
    tdr = ("Servicio de asistencia logística para eventos. Dos pantallas LED exteriores de 4 x 3 metros. "
           "Procesador LED, switcher y laptop. Transporte, instalación y desmontaje.")
    item = to_opportunity(release, tdr)
    assert item["scope"] == "Integral con componente audiovisual/técnico"
    assert {"integral", "screens", "logistics", "tv"} <= set(item["families"])
    assert any(e["origin"] == "Documento oficial" and e["family"] == "screens" for e in item["evidence"])


@pytest.mark.parametrize("text", [
    "Adquisición de cemento para La Convención - Cusco",
    "Materiales de limpieza para el Congreso de la República",
    "Servicio de lanzamiento de estructuras metálicas para puente",
    "Adquisición de panel LED de 40 W luz blanca para techo",
    "Alumbrado público con luminarias LED",
    "El arbitraje se realiza en un foro de reputación reconocida internacionalmente.",
    "Precio por activación o mixta para el contrato de contingencia.",
    "Sistema de registro audiovisual de acceso para la vigilancia de las villas militares.",
])
def test_avoids_equipment_and_place_name_false_positives(text):
    assert match_text(text) == []


def test_keeps_real_convention_and_led_screen():
    assert match_text("Organización de una convención empresarial con pantallas LED")


def test_boilerplate_does_not_hide_a_later_real_event_occurrence():
    text = "Foro de reputación reconocida para arbitraje. " + "Documento legal. " * 30 + "Organización de foro empresarial."
    result = match_text(text, "Documento oficial")
    assert any(e["term"] == "foro" and "empresarial" in e["snippet"] for e in result)


def test_zero_or_reserved_amount_is_not_advertised_as_a_free_contract(release):
    release["tender"]["value"]["amount"] = 0
    release["tender"]["hasTenderInformationProtectedByLaw"] = True
    assert to_opportunity(release)["amount"] is None


def test_incidental_document_event_words_do_not_change_commercial_object(release):
    release["tender"]["description"] = "Adquisición de pantalla LED para centro de control"
    item = to_opportunity(release, "Anexo: experiencia en ferias y equipos en modo stand by.")
    assert item["scope"] == "Servicio o equipo específico"


def test_supplier_address_does_not_determine_service_city(release):
    release["parties"][0]["address"] = {"department": "Puno", "region": "Puno"}
    release["parties"].append({"id": "supplier", "roles": ["supplier"], "address": {"region": "Lima"}})
    item = to_opportunity(release)
    assert item["city"] == "Otras zonas"
    assert "Domicilio" in item["location_basis"]


def test_service_place_takes_precedence_over_buyer(release):
    release["tender"]["items"] = [{"description": "Servicio de evento", "deliveryAddress": {"region": "Trujillo"}}]
    item = to_opportunity(release)
    assert item["city"] == "Trujillo"
    assert item["location_basis"].startswith("Lugar de prestación")


def test_document_place_takes_precedence_over_buyer(release):
    item = to_opportunity(release, "Lugar de prestación: ciudad de Arequipa, local institucional.")
    assert item["city"] == "Arequipa"


def test_explicit_out_of_scope_delivery_does_not_use_buyer_city(release):
    release["tender"]["deliveryAddress"] = {"region": "Puno"}
    assert to_opportunity(release)["city"] == "Otras zonas"


def test_cusco_department_is_labeled_as_reference(release):
    release["parties"][0]["address"] = {"department": "Cusco", "region": "La Convención"}
    item = to_opportunity(release)
    assert item["city"] == "Cusco"
    assert "referencia departamental" in item["location_basis"]


def test_active_state_and_future_deadline_required(release):
    assert to_opportunity(release)["classification"] == "open"
    release["tender"].pop("status")
    assert to_opportunity(release)["classification"] == "review"
    release["tender"]["tenderPeriod"].pop("endDate")
    assert to_opportunity(release)["classification"] == "review"


def test_awarded_and_cancelled_are_not_open(release):
    release["awards"] = [{"id": "award"}]
    assert to_opportunity(release)["classification"] != "open"
    release["tender"]["status"] = "complete"
    assert to_opportunity(release)["classification"] == "historical"


def test_old_source_does_not_claim_current_opportunity(release):
    release["date"] = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    assert to_opportunity(release)["classification"] == "review"


def test_deadlines_are_recomputed_when_read(db, release):
    save_release(db, release)
    row = list_items(db)[0]
    assert row["classification"] == "open"
    future = datetime.now(UTC) + timedelta(days=20)
    assert classify(row, future)[0] == "historical"


def test_updates_preserve_notes_and_ignore_publication_timestamp_only(db, release):
    save_release(db, release)
    original = db.opportunity(release["ocid"])
    with db.connect() as conn:
        conn.execute("UPDATE opportunities SET stage='Cotizar',notes='Preparar presupuesto' WHERE ocid=?", (release["ocid"],))
    newer = deepcopy(release)
    newer["date"] = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    save_release(db, newer)
    row = db.opportunity(release["ocid"])
    assert row["stage"] == "Cotizar" and row["notes"] == "Preparar presupuesto"
    assert row["version"] == original["version"]
    newer["tender"]["value"]["amount"] = 25000
    save_release(db, newer)
    assert db.opportunity(release["ocid"])["version"] != original["version"]

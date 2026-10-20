"""Vocabulary, geography and conservative OCDS interpretation. No AI/API keys required."""

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from .config import OFFICIAL_BASE

FAMILIES = {
    "integral": ("Producción integral", [
        "organización de eventos", "producción de eventos", "ejecución de eventos", "realización de eventos",
        "servicio integral de eventos", "organización y desarrollo de eventos", "producción técnica",
        "operación técnica de eventos", "organización y ejecución", "organización, producción",
        "planificación y desarrollo de eventos", "evento corporativo", "eventos corporativos",
    ]),
    "institutional": ("Eventos institucionales", [
        "evento institucional", "eventos institucionales", "evento protocolar", "ceremonia", "acto protocolar",
        "inauguración", "clausura", "aniversario institucional", "lanzamiento", "presentación institucional",
        "premiación", "fiesta de fin de año", "fiestas de fin de año", "celebración institucional",
    ]),
    "meetings": ("Congresos y encuentros", [
        "congreso", "convención", "conferencia", "seminario", "simposio", "foro", "encuentro empresarial",
        "cumbre", "conversatorio", "rueda de negocios", "jornada institucional",
    ]),
    "fairs": ("Ferias y actividades públicas", [
        "organización de ferias", "feria", "ferias", "exposición", "activación", "campaña informativa",
        "campaña de sensibilización", "actividad cultural", "festival", "stand", "stands",
    ]),
    "logistics": ("Logística y montaje", [
        "asistencia logística", "soporte logístico", "apoyo logístico", "implementación de eventos",
        "acondicionamiento de espacios", "montaje y desmontaje", "infraestructura temporal",
        "equipamiento para eventos", "logística para eventos", "logística de eventos",
    ]),
    "av": ("Equipos audiovisuales", [
        "equipos audiovisuales", "equipamiento audiovisual", "soporte audiovisual", "implementación audiovisual",
        "sistema audiovisual", "equipamiento multimedia", "alquiler audiovisual",
    ]),
    "screens": ("Pantallas LED y proyección", [
        "pantalla led", "pantallas led", "pantalla gigante", "pantallas gigantes", "panel led", "paneles led",
        "videowall", "video wall", "pantalla modular", "pantallas modulares", "proyección multimedia",
        "proyector multimedia", "proyectores multimedia", "ecran", "monitor de retorno", "televisor de retorno",
        "alquiler de pantalla", "alquiler de pantallas", "servicio de pantalla", "procesador led",
    ]),
    "sound": ("Sonido profesional", [
        "alquiler de sonido", "sistema de sonido", "sonorización", "amplificación de sonido", "sonido profesional",
        "refuerzo sonoro", "audio para eventos", "microfonía", "micrófonos inalámbricos", "consola de audio",
    ]),
    "lighting": ("Iluminación y estructuras", [
        "iluminación profesional", "iluminación escénica", "luces para eventos", "iluminación de escenario",
        "estructuras para iluminación", "truss", "escenario", "tarima", "rigging",
    ]),
    "streaming": ("Transmisión y streaming", [
        "transmisión en vivo", "transmisión en directo", "streaming", "transmisión por internet", "retransmisión",
        "transmisión multicámara", "circuito cerrado de televisión para eventos",
    ]),
    "hybrid": ("Eventos virtuales e híbridos", [
        "evento virtual", "evento híbrido", "conferencia virtual", "webinar", "seminario virtual",
        "plataforma para eventos", "operación de videoconferencias", "soporte técnico para reuniones virtuales",
    ]),
    "production": ("Producción audiovisual", [
        "producción audiovisual", "realización audiovisual", "producción de videos", "elaboración de videos",
        "video institucional", "video corporativo", "video promocional", "spot audiovisual", "cápsulas audiovisuales",
        "contenido audiovisual", "producción de video", "elaboración de video",
    ]),
    "coverage": ("Grabación y cobertura", [
        "registro audiovisual", "cobertura audiovisual", "cobertura de eventos", "filmación", "grabación de video",
        "registro fílmico", "registro fotográfico", "fotografía y video", "memoria audiovisual",
    ]),
    "tv": ("Televisión y unidades móviles", [
        "producción televisiva", "realización televisiva", "grabación multicámara", "unidad de transmisión",
        "sistema de realización", "switcher de video", "switcher", "cámaras profesionales", "teleprompter",
    ]),
    "studio": ("Estudios y espacios", [
        "alquiler de estudio", "estudio de televisión", "estudio de grabación", "set de televisión",
        "set audiovisual", "estudio para podcast", "estudio de fotografía", "locación para producción",
    ]),
    "post": ("Posproducción", [
        "edición de video", "montaje audiovisual", "posproducción", "postproducción", "motion graphics",
        "subtitulado", "locución", "edición de audio", "adaptación de piezas audiovisuales",
    ]),
    "communication": ("Comunicación y publicidad", [
        "servicio de comunicación", "campaña comunicacional", "producción de contenidos", "contenido digital",
        "piezas comunicacionales", "material audiovisual", "difusión institucional", "producción publicitaria",
        "piezas audiovisuales",
    ]),
    "crew": ("Personal técnico", [
        "operador de sonido", "operador de video", "técnico audiovisual", "camarógrafo", "realizador audiovisual",
        "director de cámaras", "técnico de iluminación", "operador de streaming", "asistencia técnica audiovisual",
    ]),
}
INTEGRAL = {"integral", "institutional", "meetings", "fairs", "logistics"}
TECHNICAL = set(FAMILIES) - INTEGRAL


def normalize(text):
    value = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", value).strip()


PATTERNS = {
    key: [(term, re.compile(r"(?<!\w)" + re.escape(normalize(term)) + r"(?!\w)")) for term in terms]
    for key, (_, terms) in FAMILIES.items()
}


def match_text(text, origin="Objeto e ítems"):
    flat = normalize(text)
    # Administrative names and civil-engineering uses are not event requests.
    # Keep text offsets by replacing with spaces, preserving evidence snippets from the original text.
    searchable = flat
    exclusions = [r"\bcongreso de la republica\b", r"\bla convencion\b(?!\s+(?:internacional|nacional|empresarial|anual))",
                  r"\blanzamiento\s+de\s+(?:estructuras?|puentes?|vigas?)\b",
                  r"\bregistro audiovisual de acceso\b", r"\bstand[ -]+by\b"]
    for pattern in exclusions:
        searchable = re.sub(pattern, lambda m: " " * len(m.group()), searchable)
    results = []
    for key, patterns in PATTERNS.items():
        for term, pattern in patterns:
            found = None
            for match in pattern.finditer(searchable):
                context = flat[max(0, match.start() - 100):match.end() + 150]
                term_norm = normalize(term)
                if term_norm == "foro" and re.search(r"arbitral|arbitraje|reputacion reconocida", context):
                    continue
                if term_norm == "activacion" and re.search(r"contingencia|poliza|aseguradora", context):
                    continue
                if term_norm == "escenario" and re.search(r"escenario(?:s)? (?:de riesgo|hipotetico|adverso|de desastre)", context):
                    continue
                # Do not treat LED lamps or building panels as event screens.
                if key == "screens" and term_norm in ("panel led", "paneles led"):
                    if re.search(r"luminaria|alumbrado|luz blanca|[0-9]+\s*w\b|techo", context):
                        continue
                found = match
                break
            if found:
                results.append({"family": key, "label": FAMILIES[key][0], "term": term,
                                "origin": origin, "snippet": flat[max(0, found.start() - 85):found.end() + 150]})
                break
    return results


def parse_date(value):
    try:
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def classify(item, now=None):
    now = now or datetime.now(UTC)
    deadline = parse_date(item.get("deadline"))
    if item.get("has_awards") or item.get("has_contracts"):
        if item.get("tender_status") == "active":
            return "review", "El proceso contiene adjudicaciones o contratos; revisar si quedan ítems abiertos."
        return "historical", "El registro ya contiene adjudicaciones o contratos."
    if item.get("tender_status") in ("cancelled", "unsuccessful", "complete", "withdrawn"):
        return "historical", "La fuente indica que el procedimiento terminó o fue cancelado."
    if deadline and deadline <= now:
        return "historical", "La fecha de cierre publicada ya pasó."
    if not deadline:
        return "review", "La fuente no publica una fecha de cierre verificable."
    if item.get("tender_status") != "active":
        return "review", "Hay una fecha futura, pero falta un estado activo explícito en la fuente."
    if not parse_date(item.get("source_updated")) or parse_date(item["source_updated"]) < now - timedelta(days=7):
        return "review", "El registro de origen tiene más de 7 días; confirmar el estado en SEACE."
    return "open", "Estado activo y plazo futuro según el registro consultado; confirmar requisitos en SEACE."


def city_from_address(address):
    if not isinstance(address, dict):
        return None, ""
    locality = normalize(address.get("locality"))
    province = normalize(address.get("region"))
    department = normalize(address.get("department"))
    postal = str(address.get("postalCode") or "")
    for city, prefix in [("Lima", "1501"), ("Cusco", "0801"), ("Trujillo", "1301"), ("Arequipa", "0401")]:
        name = normalize(city)
        names = {name, "cuzco"} if city == "Cusco" else {name}
        if province in names or locality in names or (postal.isdigit() and postal.startswith(prefix)):
            return city, "provincia/localidad"
        if department in names:
            return city, "referencia departamental"
    return None, ""


def locate(release, document_text=""):
    tender = release.get("tender") or {}
    delivery = []
    for item in tender.get("items") or []:
        if item.get("deliveryAddress"):
            delivery.append(item["deliveryAddress"])
        for place in item.get("deliveryLocations") or []:
            delivery.append(place.get("address") or {})
    if tender.get("deliveryAddress"):
        delivery.append(tender["deliveryAddress"])
    for address in delivery:
        city, detail = city_from_address(address)
        if city:
            return city, "Lugar de prestación · " + detail, address
    if delivery and any(a.get("department") or a.get("region") or a.get("locality") for a in delivery):
        return "Otras zonas", "Lugar de prestación publicado fuera de las cuatro zonas", delivery[0]
    # Accept only an explicit place-of-service passage; a passing city name is not location evidence.
    normalized = normalize(document_text + " " + (tender.get("description") or ""))
    for place in re.finditer(r"(?:lugar de (?:prestacion|ejecucion|realizacion|entrega)|ubicacion del evento)\s*[:.\-]?(.{0,200})",
                             normalized):
        for city in ("Lima", "Cusco", "Trujillo", "Arequipa"):
            pattern = r"\b(?:cusco|cuzco)\b" if city == "Cusco" else r"\b" + normalize(city) + r"\b"
            if re.search(pattern, place.group(1)):
                return city, "Lugar de prestación · texto del requerimiento", {}
    buyer = release.get("buyer") or tender.get("procuringEntity") or {}
    for party in release.get("parties") or []:
        if party.get("id") == buyer.get("id") or "buyer" in (party.get("roles") or []):
            address = party.get("address") or {}
            city, detail = city_from_address(address)
            if city:
                return city, "Domicilio de la entidad · " + detail + " (confirmar lugar del servicio)", address
            if address.get("department") or address.get("region") or address.get("locality"):
                return "Otras zonas", "Domicilio de la entidad fuera de las cuatro zonas; lugar del servicio por confirmar", address
    return None, "Sin ubicación confirmada", {}


def to_opportunity(release, document_text="", documents_info=None):
    ocid = release.get("ocid")
    if not isinstance(ocid, str) or not ocid:
        return None
    tender = release.get("tender") or {}
    text = "\n".join(str(x or "") for x in [
        tender.get("title"), tender.get("description"),
        *[i.get("description") for i in tender.get("items") or []],
    ])
    evidence = match_text(text)
    if document_text:
        evidence += match_text(document_text, "Documento oficial")
    if not evidence:
        return None
    families = sorted({e["family"] for e in evidence})
    if tender.get("mainProcurementCategory") == "works" and not set(families) & {
        "av", "screens", "sound", "streaming", "production", "coverage", "tv", "studio", "post"
    }:
        return None
    # The commercial object determines whether this is an integral contract. Incidental event
    # words in legal annexes must not turn a screen purchase into event production.
    source_families = {e["family"] for e in evidence if e["origin"] == "Objeto e ítems"}
    integral = bool(source_families & INTEGRAL)
    technical = bool(set(families) & TECHNICAL)
    scope = ("Integral con componente audiovisual/técnico" if integral and technical else
             "Integral · revisar componente técnico" if integral else "Servicio o equipo específico")
    docs = []
    for doc in tender.get("documents") or []:
        if isinstance(doc.get("url"), str) and doc["url"].startswith("https://"):
            docs.append({"title": doc.get("title") or "Documento oficial", "url": doc["url"],
                         "format": doc.get("format", ""), "type": doc.get("documentType", ""),
                         "date": doc.get("dateModified") or doc.get("datePublished") or ""})
    city, basis, address = locate(release, document_text)
    value = tender.get("value") or {}
    amount = value.get("amount")
    if not isinstance(amount, (int, float)) or amount <= 0:
        amount = None
    buyer = release.get("buyer") or tender.get("procuringEntity") or {}
    buyer_party = next((p for p in release.get("parties") or [] if p.get("id") == buyer.get("id")), {})
    suppliers = sorted({s.get("name", "") for a in release.get("awards") or [] for s in a.get("suppliers") or []} - {""})
    result = {
        "ocid": ocid, "reference": tender.get("title") or ocid,
        "title": tender.get("description") or tender.get("title") or "Sin descripción publicada",
        "buyer": buyer.get("name") or "Entidad no publicada", "buyer_id": buyer.get("id", ""),
        "buyer_address": buyer_party.get("address") or {},
        "buyer_contact": buyer_party.get("contactPoint") or {},
        "city": city, "location_basis": basis, "service_address": address,
        "amount": amount, "currency": value.get("currency") or "", "families": families,
        "evidence": evidence, "scope": scope, "documents": docs,
        "deadline": (tender.get("tenderPeriod") or {}).get("endDate"),
        "published": tender.get("datePublished") or (tender.get("tenderPeriod") or {}).get("startDate"),
        "source_updated": release.get("date"), "tender_status": tender.get("status", ""),
        "has_awards": bool(release.get("awards")), "has_contracts": bool(release.get("contracts")),
        "suppliers": suppliers, "method": tender.get("procurementMethodDetails", ""),
        "url": OFFICIAL_BASE + "/proceso/" + quote(ocid, safe=""),
        "raw_url": OFFICIAL_BASE + "/api/v1/record/" + quote(ocid, safe=""),
        "document_checks": documents_info or [],
        "score": min(100, (40 if technical else 18) + (20 if integral and technical else 0)
                     + min(len(families) * 5, 25) + (10 if any(e["origin"] == "Documento oficial" for e in evidence) else 0)),
    }
    result["classification"], result["status_reason"] = classify(result)
    return result

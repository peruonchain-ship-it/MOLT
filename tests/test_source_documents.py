import io
import json
from copy import deepcopy

import httpx
import pytest
from pypdf import PdfWriter

from molt.documents import allowed_document_url, extract_pdf, process_documents
from molt.source import OfficialClient, SourceError, SyncService, save_release

from .conftest import text_pdf


class Pages:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        item = next(self.pages)
        if isinstance(item, Exception):
            raise item
        return item


def package(release, next_url=None):
    return {"records": [{"compiledRelease": release}], "links": {"next": next_url}}


def test_sync_follows_cursor_and_deduplicates(db, release):
    next_url = "https://contratacionesabiertas.oece.gob.pe/api/v1/recordsAfter?searchAfter=test"
    client = Pages([package(release, next_url), package(release)])
    result = SyncService(db, client).run()
    assert result["status"] == "complete" and result["scanned"] == 2
    assert client.calls[1] == next_url
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1


def test_partial_sync_is_not_complete_and_resumes(db, release):
    cursor = "https://contratacionesabiertas.oece.gob.pe/api/v1/recordsAfter?searchAfter=checkpoint"
    first = SyncService(db, Pages([package(release, cursor)])).run(max_pages=1)
    assert first["status"] == "partial"
    assert db.sync_status()["last_complete"] is None
    client = Pages([package(release)])
    second = SyncService(db, client).run()
    assert client.calls == [cursor]
    assert second["status"] == "complete" and second["scanned"] == 2


def test_failed_source_keeps_old_records_and_explains_error(db, release):
    save_release(db, release)
    result = SyncService(db, Pages([SourceError("HTTP 503 de prueba")])).run()
    assert result["status"] == "error"
    assert db.opportunity(release["ocid"])
    assert db.sync_status()["last_complete"] is None


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "https://evil.example/api/v1/recordsAfter",
                                      "https://contratacionesabiertas.oece.gob.pe.evil.example/api/v1/x",
                                      "https://user:pass@contratacionesabiertas.oece.gob.pe/api/v1/x"])
def test_source_rejects_untrusted_next_links(url):
    with pytest.raises(SourceError):
        OfficialClient().get(url)


def test_document_fetch_has_strict_https_destination_policy():
    assert allowed_document_url("https://prod1.seace.gob.pe/document.pdf")
    assert not allowed_document_url("https://evil-seace.gob.pe/document.pdf")
    assert not allowed_document_url("http://prod1.seace.gob.pe/document.pdf")
    assert not allowed_document_url("https://prod1.seace.gob.pe:8080/document.pdf")
    assert not allowed_document_url("https://127.0.0.1/document.pdf")


def test_pdf_text_is_read_and_changes_opportunity_scope(db, release):
    pdf = text_pdf("Dos pantallas LED exteriores de 4 x 3 metros, procesador LED, switcher y laptop para el evento.")
    status, text, detail = extract_pdf(pdf)
    assert status == "read" and "pantallas LED" in text and "1/1" in detail
    release["tender"]["documents"] = [{"url": "https://prod1.seace.gob.pe/tdr.pdf", "title": "Términos de referencia", "documentType": "technicalSpecifications"}]
    save_release(db, release)
    result = process_documents(db, 1, fetcher=lambda _: pdf)
    assert result["processed"] == 1
    item = json.loads(db.opportunity(release["ocid"])["data"])
    assert "screens" in item["families"]
    assert item["scope"] == "Integral con componente audiovisual/técnico"
    assert item["document_checks"][0]["status"] == "read"


def test_sync_requires_pagination_evidence(db, release):
    broken = deepcopy(package(release))
    broken.pop("links")
    assert SyncService(db, Pages([broken])).run()["status"] == "error"


def test_scanned_or_blank_pdf_is_manual_review():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    content = io.BytesIO()
    writer.write(content)
    status, text, detail = extract_pdf(content.getvalue())
    assert status == "manual" and not text and "OCR" in detail


def test_changed_attachment_invalidates_previous_equipment_evidence(db, release):
    doc = {"url": "https://prod1.seace.gob.pe/tdr.pdf", "title": "TDR", "documentType": "technicalSpecifications",
           "datePublished": "2026-01-01T00:00:00-05:00"}
    release["tender"]["documents"] = [doc]
    save_release(db, release)
    pdf = text_pdf("Se requieren dos pantallas LED exteriores, un procesador LED y switcher de video para operar.")
    process_documents(db, 1, fetcher=lambda _: pdf)
    assert "screens" in json.loads(db.opportunity(release["ocid"])["data"])["families"]
    doc["dateModified"] = "2026-02-01T00:00:00-05:00"
    save_release(db, release)
    item = json.loads(db.opportunity(release["ocid"])["data"])
    assert "screens" not in item["families"]
    assert item["document_checks"][0]["status"] == "pending"


def test_zip_is_manual_without_download(db, release):
    release["tender"]["documents"] = [{"url": "https://prod1.seace.gob.pe/propuestas", "title": "Bases",
                                         "documentType": "biddingDocuments", "format": "zip"}]
    save_release(db, release)
    assert process_documents(db, 1, fetcher=lambda _: pytest.fail("No se debe descargar ZIP"))["processed"] == 0
    item = json.loads(db.opportunity(release["ocid"])["data"])
    assert item["document_checks"][0]["status"] == "manual"


def test_proxy_block_pauses_document_queue_until_explicit_retry(db, release):
    release["tender"]["documents"] = [{"url": "https://prod1.seace.gob.pe/tdr.pdf", "title": "TDR",
                                         "documentType": "technicalSpecifications"}]
    save_release(db, release)

    def blocked(_):
        raise httpx.ProxyError("403 Forbidden")

    process_documents(db, 1, fetcher=blocked)
    assert db.sync_status()["documents_paused"] is True
    assert process_documents(db, 1, fetcher=lambda _: pytest.fail("No debe reintentar sin cambios"))["status"] == "blocked"

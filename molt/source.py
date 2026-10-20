import json
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx

from .config import OFFICIAL_BASE, TIMEZONE
from .db import utcnow
from .matching import to_opportunity

log = logging.getLogger(__name__)


class SourceError(Exception):
    pass


class OfficialClient:
    """Only the documented official OCDS records API. Never follows arbitrary next links."""

    def get(self, url):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != "contratacionesabiertas.oece.gob.pe"
                or parsed.port not in (None, 443) or not parsed.path.startswith("/api/v1/")
                or parsed.username or parsed.password):
            raise SourceError("La API devolvió un enlace fuera del origen oficial permitido.")
        for attempt in range(3):
            try:
                with httpx.Client(timeout=45, follow_redirects=False, headers={"User-Agent": "MOLT/0.1 (OCDS reader)"}) as client:
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 24 * 1024 * 1024:
                                raise SourceError("La página de la API excede el límite de 24 MB.")
                result = json.loads(data)
                if not isinstance(result, dict) or not isinstance(result.get("records"), list):
                    raise SourceError("La fuente no devolvió un paquete de registros OCDS válido.")
                return result
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise SourceError(f"El portal oficial respondió HTTP {status}. Se conservan los datos previos.") from None
            except (httpx.RequestError, json.JSONDecodeError):
                if attempt == 2:
                    raise SourceError("No se pudo leer la API oficial. Verifica conectividad y disponibilidad.") from None
            time.sleep(0.5 * (attempt + 1))
        raise SourceError("La fuente no respondió.")


def document_data(db, ocid):
    with db.connect() as conn:
        docs = conn.execute("SELECT title,url,status,text,detail,checked_at FROM documents WHERE ocid=?", (ocid,)).fetchall()
    text = "\n".join(d["text"] for d in docs if d["status"] in ("read", "partial"))
    info = [{k: row[k] for k in ("title", "url", "status", "detail", "checked_at")} for row in docs]
    return text, info


def save_release(db, release):
    text, info = document_data(db, release.get("ocid", ""))
    item = to_opportunity(release, text, info)
    if item:
        candidate_urls = []
        for doc in item["documents"]:
            # PDFs are candidates; ZIP/scanned/other types remain visible as manual review.
            if doc["type"] in ("biddingDocuments", "technicalSpecifications", "evaluationCriteria") or any(
                word in doc["title"].lower() for word in ("referencia", "tdr", "bases", "requerimiento", "especificaciones")
            ):
                candidate_urls.append(doc["url"])
                db.queue_document(item["ocid"], doc)
        with db.connect() as conn:
            if candidate_urls:
                marks = ",".join("?" for _ in candidate_urls)
                conn.execute(f"DELETE FROM documents WHERE ocid=? AND url NOT IN ({marks})",
                             (item["ocid"], *candidate_urls))
            else:
                conn.execute("DELETE FROM documents WHERE ocid=?", (item["ocid"],))
        # Changed/removed attachments must not keep contributing stale document evidence.
        text, info = document_data(db, item["ocid"])
        item = to_opportunity(release, text, info)
        if item:
            db.upsert(item, release)
    return item


class SyncService:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or OfficialClient()

    def run(self, max_pages=200):
        owner = self.db.lease("sync")
        if not owner:
            return {"status": "busy", "message": "Ya hay una sincronización en curso."}
        run_id = None
        try:
            settings = self.db.settings()
            today = datetime.now(ZoneInfo(TIMEZONE)).date()
            start = (today - timedelta(days=settings["lookback_days"])).isoformat()
            end = today.isoformat()
            url = OFFICIAL_BASE + "/api/v1/recordsAfter?" + urlencode({
                "size": 100, "startDate": start, "endDate": end,
            })
            pages = scanned = matched = 0
            latest = None
            with self.db.connect() as conn:
                previous = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
                if (previous and previous["status"] in ("partial", "error", "running")
                        and previous["next_url"] and previous["window_start"] == start
                        and previous["window_end"] == end):
                    url = previous["next_url"]
                    pages, scanned, matched = previous["pages"], previous["scanned"], previous["matched"]
                    latest = previous["source_latest"]
                run_id = conn.execute("""INSERT INTO sync_runs
                    (started_at,status,pages,scanned,matched,window_start,window_end,next_url,source_latest)
                    VALUES (?,?,?,?,?,?,?,?,?) RETURNING id""",
                    (utcnow(), "running", pages, scanned, matched, start, end, url, latest)).fetchone()[0]
            visited = set()
            with self.db.connect() as conn:
                with_documents = {row[0] for row in conn.execute("SELECT DISTINCT ocid FROM documents")}
            for _ in range(max_pages):
                if not url:
                    break
                if url in visited:
                    raise SourceError("La fuente repitió un cursor. Consulta incompleta; no se declara cobertura total.")
                visited.add(url)
                package = self.client.get(url)
                records = package["records"]
                for record in records:
                    release = record.get("compiledRelease")
                    if not isinstance(release, dict) or not release.get("ocid"):
                        raise SourceError("Un registro no contiene compiledRelease/ocid. Revisión de formato pendiente.")
                    # Avoid a database round trip for every unrelated government purchase.
                    if ((release["ocid"] in with_documents or to_opportunity(release))
                            and save_release(self.db, release)):
                        matched += 1
                    date = release.get("date")
                    if date and (not latest or date > latest):
                        latest = date
                if not isinstance(package.get("links"), dict) or "next" not in package["links"]:
                    raise SourceError("La API no informa el fin de la paginación; cobertura sin confirmar.")
                next_url = package["links"]["next"]
                if next_url and not isinstance(next_url, str):
                    raise SourceError("Cursor de paginación no válido.")
                url = next_url
                pages += 1
                scanned += len(records)
                with self.db.connect() as conn:
                    conn.execute("""UPDATE sync_runs SET pages=?,scanned=?,matched=?,next_url=?,source_latest=?
                        WHERE id=?""", (pages, scanned, matched, url, latest, run_id))
                self.db.renew("sync", owner)
                if not records and url:
                    raise SourceError("La fuente devolvió una página vacía con continuación. Revisión pendiente.")
            status = "partial" if url else "complete"
            message = ("Consulta parcial: se reanudará desde el cursor guardado." if url else
                       "Ventana consultada completa. Los documentos pendientes se revisan por separado.")
            with self.db.connect() as conn:
                conn.execute("UPDATE sync_runs SET status=?,message=?,finished_at=? WHERE id=?",
                             (status, message, utcnow(), run_id))
            return {"status": status, "scanned": scanned, "matched": matched, "pages": pages}
        except Exception as exc:
            message = str(exc) if isinstance(exc, SourceError) else "Error interno al consultar la fuente. Revisa los registros del servidor."
            if not isinstance(exc, SourceError):
                log.exception("Error de sincronización")
            if run_id:
                with self.db.connect() as conn:
                    conn.execute("UPDATE sync_runs SET status='error',message=?,finished_at=? WHERE id=?",
                                 (message, utcnow(), run_id))
            return {"status": "error", "message": message}
        finally:
            self.db.release("sync", owner)

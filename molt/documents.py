import hashlib
import io
import json
from urllib.parse import urljoin, urlparse

import httpx
from pypdf import PdfReader

from .db import utcnow
from .matching import to_opportunity
from .source import document_data

MAX_BYTES = 12 * 1024 * 1024
MAX_PAGES = 160
MAX_TEXT = 400_000


class DocumentError(Exception):
    pass


def allowed_document_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return (parsed.scheme == "https" and parsed.port in (None, 443)
                and not parsed.username and not parsed.password
                and (host == "contratacionesabiertas.oece.gob.pe" or host.endswith(".seace.gob.pe")))
    except ValueError:
        return False


def fetch_pdf(url):
    with httpx.Client(timeout=35, follow_redirects=False, headers={"User-Agent": "MOLT/0.1 (document reader)"}) as client:
        for _ in range(4):
            if not allowed_document_url(url):
                raise DocumentError("Destino no permitido para lectura automática. Revisar el enlace oficial manualmente.")
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code != 200:
                    raise DocumentError(f"Documento no disponible (HTTP {response.status_code}). Revisar en SEACE.")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_BYTES:
                        raise DocumentError("Documento mayor a 12 MB: requiere revisión manual.")
                if not bytes(content).lstrip().startswith(b"%PDF-"):
                    raise DocumentError("El enlace no entrega un PDF legible (puede ser ZIP, HTML o requerir acceso manual).")
                return bytes(content)
    raise DocumentError("El documento excedió el límite de redirecciones.")


def extract_pdf(content):
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise DocumentError("PDF protegido: requiere revisión manual.")
        parts, length = [], 0
        total = len(reader.pages)
        processed = 0
        for page in reader.pages[:MAX_PAGES]:
            text = page.extract_text() or ""
            parts.append(text)
            length += len(text)
            processed += 1
            if length > MAX_TEXT:
                break
        text = "\n".join(parts)[:MAX_TEXT]
        if len(text.strip()) < 40:
            return "manual", "", "PDF sin texto suficiente; puede ser escaneado. Requiere OCR o revisión manual."
        partial = total > processed or length > MAX_TEXT
        detail = f"Texto extraído de {processed}/{total} páginas."
        if partial:
            detail += " Lectura parcial por límite de tamaño; revisar el documento completo."
        return "partial" if partial else "read", text, detail
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("No se pudo interpretar el PDF. Requiere revisión manual.") from None


def process_documents(db, limit=4, fetcher=fetch_pdf, ocid=None, force=False):
    if db.settings().get("documents_paused") and not force:
        return {"status": "blocked", "processed": 0}
    if force:
        db.save_settings({"documents_paused": False, "documents_message": ""})
    owner = db.lease("documents", seconds=600)
    if not owner:
        return {"status": "busy", "processed": 0}
    processed = 0
    try:
        with db.connect() as conn:
            condition = " AND d.ocid=?" if ocid else ""
            params = (ocid, limit) if ocid else (limit,)
            docs = conn.execute("""SELECT d.* FROM documents d JOIN opportunities o ON d.ocid=o.ocid
                WHERE d.status='pending'""" + condition + """ ORDER BY
                CASE WHEN json_extract(o.data,'$.city') IN ('Lima','Cusco','Trujillo','Arequipa')
                    THEN 0 ELSE 1 END, o.first_seen DESC,d.key LIMIT ?""", params).fetchall()
        for doc in docs:
            blocked = False
            try:
                status, text, detail = extract_pdf(fetcher(doc["url"]))
            except DocumentError as exc:
                status, text, detail = "manual", "", str(exc)
            except httpx.ProxyError:
                status, text = "error", ""
                detail = "El proxy no permite acceder a los adjuntos SEACE. Habilita el destino en la red y reintenta."
                db.save_settings({"documents_paused": True, "documents_message": detail})
                blocked = True
            except httpx.RequestError:
                status, text, detail = "error", "", "No se pudo conectar con el documento. Puedes reintentar su revisión."
            with db.connect() as conn:
                conn.execute("UPDATE documents SET status=?,text=?,detail=?,checked_at=?,attempts=attempts+1 WHERE key=?",
                             (status, text, detail, utcnow(), doc["key"]))
            row = db.opportunity(doc["ocid"])
            if row:
                all_text, info = document_data(db, doc["ocid"])
                release = json.loads(row["raw"])
                item = to_opportunity(release, all_text, info)
                if item:
                    db.upsert(item, release)
            processed += 1
            db.renew("documents", owner, seconds=600)
            if blocked:
                break
        return {"status": "complete", "processed": processed}
    finally:
        db.release("documents", owner)


def reset_documents(db, ocid):
    with db.connect() as conn:
        conn.execute("UPDATE documents SET status='pending' WHERE ocid=? AND status IN ('error','manual','partial')", (ocid,))
    # The next background cycle processes only the stored official attachment URLs.
    return hashlib.sha256(ocid.encode()).hexdigest()[:8]

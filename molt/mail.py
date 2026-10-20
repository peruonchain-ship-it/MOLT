import base64
import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import TIMEZONE
from .db import utcnow
from .export import CLASS_LABELS, spreadsheet
from .matching import parse_date
from .repository import list_items


def valid_email(value):
    return bool(re.fullmatch(r"[^\s@<>,;\r\n]+@[^\s@<>,;\r\n]+\.[^\s@<>,;\r\n]+", value or ""))


def mail_status(db):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM mail_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {"configured": bool(db.config.mail_key and db.config.mail_from),
            "key_present": bool(db.config.mail_key), "sender_present": bool(db.config.mail_from),
            "recipient": db.settings()["email_to"], "last_run": dict(row) if row else None}


def digest_items(db):
    settings = db.settings()
    recipient = hashlib.sha256(settings["email_to"].lower().encode()).hexdigest()
    with db.connect() as conn:
        delivered = {(r[0], r[1]): r[2] for r in conn.execute(
            "SELECT ocid,version,sent_at FROM deliveries WHERE recipient=?", (recipient,))}
    now = datetime.now(UTC)
    day = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
    output = []
    for item in list_items(db, sort="score"):
        if item["stage"] == "Descartada":
            continue
        if item["classification"] == "historical" and not settings["include_historical"]:
            continue
        key = item["version"]
        reason = "Nueva coincidencia o cambio de datos"
        if (item["ocid"], key) in delivered:
            sent = parse_date(delivered[(item["ocid"], key)])
            if sent and sent.astimezone(ZoneInfo(TIMEZONE)).date().isoformat() == day:
                continue
            deadline = parse_date(item["deadline"])
            if item["classification"] != "open" or not deadline or not (now < deadline < now + timedelta(days=3)):
                continue
            key = key + ":reminder:" + day
            if (item["ocid"], key) in delivered:
                continue
            reason = "Recordatorio: cierra en menos de 72 horas"
        output.append({**item, "delivery_key": key, "notification_reason": reason})
    return output


def preview(db):
    items = digest_items(db)
    return {"recipient": db.settings()["email_to"], "count": len(items), "configured": mail_status(db)["configured"],
            "items": [{"title": i["title"], "buyer": i["buyer"], "classification": i["classification"],
                       "notification_reason": i["notification_reason"]} for i in items[:10]]}


def build_payload(db, items):
    day = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y")
    cards = []
    lines = [f"MOLT · Radar de eventos · {day}", f"{len(items)} novedades o recordatorios.", ""]
    for item in items[:12]:
        lines.extend([f"[{CLASS_LABELS[item['classification']]}] {item['title']}",
                      f"{item['buyer']} · {item['city'] or 'Sin confirmar'}", item["url"], ""])
        cards.append(f"<tr><td style='padding:18px 0;border-bottom:1px solid #dce5df'>"
                     f"<p style='color:#46745e'>{html.escape(CLASS_LABELS[item['classification']])}</p>"
                     f"<h3>{html.escape(item['title'])}</h3><p>{html.escape(item['buyer'])}</p>"
                     f"<p>{html.escape(item['city'] or 'Sin confirmar')} · {html.escape(item['scope'])}</p>"
                     f"<a href='{html.escape(item['url'], quote=True)}'>Revisar proceso oficial →</a></td></tr>")
    footer = ("El Excel incluye todas las novedades de este resumen. Los registros por verificar no confirman "
              "que puedas participar. Revisa cronograma, bases y requisitos en SEACE. El domicilio de la entidad "
              "puede ser distinto del lugar del servicio. No se presupone autorización para subcontratar.")
    lines.append(footer)
    body = ("<html><body style='background:#f5f6f2;color:#17372c;font-family:Arial,sans-serif;padding:24px'>"
            "<div style='max-width:680px;margin:auto'><p>MOLT / TU RADAR PRIVADO</p>"
            f"<h1>Tu próxima oportunidad,<br>más cerca.</h1><p>{day} · {len(items)} novedades o recordatorios.</p>"
            "<table style='width:100%'>" + "".join(cards) + "</table>"
            f"<p style='font-size:12px;color:#65766a'>{footer}</p></div></body></html>")
    return {"from": db.config.mail_from, "to": [db.settings()["email_to"]],
            "subject": f"MOLT · {len(items)} novedades para eventos · {day}",
            "text": "\n".join(lines), "html": body,
            "attachments": [{"filename": "MOLT-oportunidades.xlsx",
                             "content": base64.b64encode(spreadsheet(items, db.sync_status())).decode()}]}


def send_digest(db, scheduled_day=None, transport=None):
    owner = db.lease("mail", seconds=180)
    if not owner:
        return {"status": "busy", "message": "Ya se está preparando un correo."}
    count = 0
    try:
        settings = db.settings()
        if not valid_email(settings["email_to"]):
            return {"status": "blocked", "message": "Configura un correo de destino válido en Preferencias."}
        if not (db.config.mail_key and db.config.mail_from):
            return {"status": "blocked", "message": "Faltan RESEND_API_KEY y/o MOLT_MAIL_FROM. Configúralos de forma segura en el servidor."}
        status = db.sync_status()
        complete = parse_date(status.get("last_complete"))
        if not complete or complete < datetime.now(UTC) - timedelta(hours=24) or status["status"] != "complete":
            return {"status": "blocked", "message": "Se necesita una consulta completa de la fuente en las últimas 24 horas antes de enviar."}
        items = digest_items(db)
        count = len(items)
        if not items:
            with db.connect() as conn:
                conn.execute("INSERT INTO mail_runs(created_at,status,count,message,scheduled_day) VALUES (?,?,?,?,?)",
                             (utcnow(), "empty", 0, "Sin novedades para enviar; no se repiten registros ya notificados.", scheduled_day))
            return {"status": "empty", "count": 0, "message": "No hay novedades pendientes de envío."}
        recipient_hash = hashlib.sha256(settings["email_to"].lower().encode()).hexdigest()
        keys = sorted((i["ocid"], i["delivery_key"]) for i in items)
        identity = hashlib.sha256(json.dumps([recipient_hash, db.config.mail_from, keys]).encode()).hexdigest()
        with db.connect() as conn:
            existing = conn.execute("SELECT payload FROM mail_outbox WHERE id=?", (identity,)).fetchone()
        if existing:
            payload = json.loads(existing[0])
        else:
            payload = build_payload(db, items)
            with db.connect() as conn:
                conn.execute("INSERT INTO mail_outbox VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING",
                             (identity, json.dumps(payload), "pending", utcnow()))
        try:
            with httpx.Client(timeout=30, transport=transport, follow_redirects=False) as client:
                response = client.post("https://api.resend.com/emails", json=payload, headers={
                    "Authorization": "Bearer " + db.config.mail_key, "Idempotency-Key": "molt-" + identity,
                })
                if response.status_code not in (200, 201) or not isinstance(response.json().get("id"), str):
                    # Provider bodies can contain user/account details; never expose raw responses or credentials.
                    raise ValueError(f"El proveedor de correo respondió HTTP {response.status_code}. Revisa la clave y el remitente autorizado.")
                provider_id = response.json()["id"]
        except httpx.RequestError:
            raise ValueError("No se confirmó la entrega al proveedor. Puedes reintentar; se conserva la clave de idempotencia.") from None
        now = utcnow()
        with db.connect() as conn:
            for item in items:
                conn.execute("INSERT INTO deliveries VALUES (?,?,?,?) ON CONFLICT(recipient,ocid,version) DO NOTHING",
                             (recipient_hash, item["ocid"], item["delivery_key"], now))
            conn.execute("UPDATE mail_outbox SET status='sent' WHERE id=?", (identity,))
            conn.execute("INSERT INTO mail_runs(created_at,status,count,message,provider_id,scheduled_day) VALUES (?,?,?,?,?,?)",
                         (now, "sent", count, "El proveedor aceptó el correo con Excel adjunto.", provider_id, scheduled_day))
        return {"status": "sent", "count": count, "message": "El proveedor aceptó el resumen y su Excel adjunto."}
    except ValueError as exc:
        with db.connect() as conn:
            conn.execute("INSERT INTO mail_runs(created_at,status,count,message,scheduled_day) VALUES (?,?,?,?,?)",
                         (utcnow(), "error", count, str(exc), scheduled_day))
        return {"status": "error", "message": str(exc)}
    finally:
        db.release("mail", owner)

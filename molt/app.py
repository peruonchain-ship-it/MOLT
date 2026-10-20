import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .auth import attempt, create_session, hash_password, require_user, verify_password
from .config import CITIES, ROOT, STAGES, Config
from .db import Database
from .documents import process_documents, reset_documents
from .export import spreadsheet
from .mail import mail_status, preview, send_digest, valid_email
from .matching import FAMILIES
from .repository import dashboard, list_items, read_item
from .source import SyncService, document_data
from .website import landing, robots, sitemap
from .worker import Worker


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class Setup(Login):
    code: str = Field(min_length=12, max_length=100)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value) < 12:
            raise ValueError("Usa al menos 12 caracteres para la contraseña.")
        return value

    @field_validator("username")
    @classmethod
    def valid_username(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,80}", value):
            raise ValueError("Usuario: de 3 a 80 letras, números o . _ @ -")
        return value


class Preferences(BaseModel):
    cities: list[str] = Field(min_length=1, max_length=4)
    email_to: str = Field(default="", max_length=254)
    email_enabled: bool = False
    digest_hour: int = Field(default=8, ge=0, le=23)
    digest_minute: int = Field(default=0, ge=0, le=59)
    include_historical: bool = False
    lookback_days: int = Field(default=90, ge=7, le=365)
    scan_interval_hours: int = Field(default=6, ge=1, le=24)

    @field_validator("cities")
    @classmethod
    def known_cities(cls, values):
        if any(v not in CITIES for v in values):
            raise ValueError("Solo Lima, Cusco, Trujillo y Arequipa en esta versión.")
        return list(dict.fromkeys(values))

    @field_validator("email_to")
    @classmethod
    def email(cls, value):
        value = value.strip()
        if value and not valid_email(value):
            raise ValueError("Ingresa un correo válido.")
        return value


class FollowUp(BaseModel):
    stage: Literal["Pendiente", "Revisar", "Cotizar", "Presentada", "Descartada"]
    notes: str = Field(default="", max_length=6000)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


def filters(
    q: str = Query("", max_length=200), city: str = "", family: str = "",
    classification: Literal["", "open", "review", "historical"] = "", stage: str = "",
    sort: Literal["recent", "deadline", "score", "amount"] = "recent", include_unknown: bool = False,
    followup: bool = False,
):
    if city and city not in (*CITIES, "unknown"):
        raise HTTPException(422, "Zona no válida.")
    if family and family not in FAMILIES:
        raise HTTPException(422, "Familia no válida.")
    if stage and stage not in STAGES:
        raise HTTPException(422, "Etapa no válida.")
    return dict(q=q, city=city, family=family, classification=classification, stage=stage, sort=sort,
                include_unknown=include_unknown, followup=followup)


def create_app(config=None):
    config = config or Config.from_env()
    db = Database(config)
    worker = Worker(db)

    @asynccontextmanager
    async def lifespan(app):
        if config.worker_enabled:
            worker.start()
        yield
        worker.close()

    app = FastAPI(title="MOLT · Radar privado", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db = db
    app.state.worker = worker
    app.state.sync = SyncService(db)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/app" or request.url.path.startswith(("/api/", "/static/", "/health")):
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
            response.headers["Cache-Control"] = "no-store"
        if config.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/health")
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "service": "molt"}

    @app.get("/")
    def index():
        return landing(config)

    @app.get("/app")
    def private_app():
        return FileResponse(ROOT / "molt/static/index.html")

    @app.get("/robots.txt", include_in_schema=False)
    def robots_txt():
        return robots(config)

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap_xml():
        return sitemap(config)

    @app.get("/api/auth/status")
    def auth_status():
        return {"initialized": db.initialized()}

    @app.post("/api/auth/setup")
    def setup(body: Setup, request: Request, response: Response):
        attempt(db, request)
        if db.initialized():
            raise HTTPException(409, "El acceso privado ya fue creado.")
        path = config.data_dir / "setup-code"
        if not path.exists() or not hmac.compare_digest(body.code, path.read_text().strip()):
            raise HTTPException(403, "Código de instalación incorrecto. Consúltalo en la consola del servidor.")
        try:
            with db.connect() as conn:
                conn.execute("INSERT INTO users VALUES (1,?,?)", (body.username, hash_password(body.password)))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "El acceso privado ya fue creado.") from None
        path.unlink(missing_ok=True)
        return {"username": body.username, "csrf": create_session(db, response)}

    @app.post("/api/auth/login")
    def login(body: Login, request: Request, response: Response):
        attempt(db, request)
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
        # Always run a password derivation, including unknown usernames, to reduce timing differences.
        encoded = row["password_hash"] if row else hash_password(secrets.token_urlsafe(20))
        valid = verify_password(body.password, encoded)
        if not row or not hmac.compare_digest(body.username, row["username"]) or not valid:
            raise HTTPException(401, "Usuario o contraseña incorrectos.")
        return {"username": row["username"], "csrf": create_session(db, response)}

    @app.get("/api/auth/me")
    def me(session=Depends(require_user)):
        with db.connect() as conn:
            username = conn.execute("SELECT username FROM users WHERE id=1").fetchone()[0]
        return {"username": username, "csrf": session["csrf"]}

    @app.post("/api/auth/logout", dependencies=[Depends(require_user)])
    def logout(request: Request, response: Response):
        token = request.cookies.get("molt_session", "")
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie("molt_session", path="/")
        return {"ok": True}

    @app.post("/api/auth/password", dependencies=[Depends(require_user)])
    def password(body: PasswordChange, response: Response):
        with db.connect() as conn:
            stored = conn.execute("SELECT password_hash FROM users WHERE id=1").fetchone()[0]
            if not verify_password(body.current_password, stored):
                raise HTTPException(403, "La contraseña actual no es correcta.")
            conn.execute("UPDATE users SET password_hash=? WHERE id=1", (hash_password(body.new_password),))
            conn.execute("DELETE FROM sessions")
        return {"csrf": create_session(db, response), "message": "Contraseña actualizada; otras sesiones cerradas."}

    @app.get("/api/dashboard", dependencies=[Depends(require_user)])
    def get_dashboard():
        return {"stats": dashboard(db), "source": db.sync_status(), "mail": mail_status(db),
                "families": {k: v[0] for k, v in FAMILIES.items()}, "cities": CITIES,
                "selected_cities": db.settings()["cities"], "stages": STAGES}

    @app.get("/api/opportunities", dependencies=[Depends(require_user)])
    def opportunities(params: Annotated[dict, Depends(filters)], offset: int = Query(0, ge=0),
                      limit: int = Query(25, ge=1, le=100)):
        items = list_items(db, **params)
        return {"total": len(items), "offset": offset, "limit": limit, "items": items[offset:offset + limit]}

    @app.get("/api/opportunities/{ocid}", dependencies=[Depends(require_user)])
    def opportunity(ocid: str):
        row = db.opportunity(ocid)
        if not row:
            raise HTTPException(404, "Oportunidad no encontrada.")
        item = read_item(row)
        _, docs = document_data(db, ocid)
        item["document_checks"] = docs
        return item

    @app.patch("/api/opportunities/{ocid}", dependencies=[Depends(require_user)])
    def followup(ocid: str, body: FollowUp):
        if not db.opportunity(ocid):
            raise HTTPException(404, "Oportunidad no encontrada.")
        with db.connect() as conn:
            conn.execute("UPDATE opportunities SET stage=?,notes=? WHERE ocid=?", (body.stage, body.notes, ocid))
        return {"ok": True}

    @app.get("/api/export.xlsx", dependencies=[Depends(require_user)])
    def export(params: Annotated[dict, Depends(filters)]):
        content = spreadsheet(list_items(db, **params), db.sync_status())
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="MOLT-oportunidades.xlsx"'})

    @app.get("/api/settings", dependencies=[Depends(require_user)])
    def settings():
        return {"settings": db.settings(), "mail": mail_status(db), "worker_enabled": config.worker_enabled}

    @app.put("/api/settings", dependencies=[Depends(require_user)])
    def save_settings(body: Preferences):
        if body.email_enabled and (not valid_email(body.email_to) or not config.mail_key or not config.mail_from):
            raise HTTPException(400, "Antes de activar los correos, configura destino, RESEND_API_KEY y MOLT_MAIL_FROM.")
        db.save_settings(body.model_dump())
        return {"ok": True, "message": "Preferencias guardadas."}

    @app.post("/api/sync", status_code=202, dependencies=[Depends(require_user)])
    def sync(background: BackgroundTasks):
        if db.lease_active("sync"):
            return {"status": "busy", "message": "La consulta ya está en curso."}
        background.add_task(app.state.sync.run)
        return {"status": "queued", "message": "Consulta iniciada. Puedes seguir usando el panel."}

    @app.post("/api/documents/process", status_code=202, dependencies=[Depends(require_user)])
    def document_batch(background: BackgroundTasks):
        with db.connect() as conn:
            conn.execute("UPDATE documents SET status='pending' WHERE status='error'")
        background.add_task(process_documents, db, 4, force=True)
        return {"status": "queued", "message": "Se revisarán hasta 4 documentos pendientes."}

    @app.post("/api/opportunities/{ocid}/documents", status_code=202, dependencies=[Depends(require_user)])
    def retry_documents(ocid: str, background: BackgroundTasks):
        if not db.opportunity(ocid):
            raise HTTPException(404, "Oportunidad no encontrada.")
        reset_documents(db, ocid)
        background.add_task(process_documents, db, 4, ocid=ocid, force=True)
        return {"status": "queued", "message": "Documentos puestos en cola. Los PDF escaneados o ZIP requieren revisión manual."}

    @app.get("/api/mail/preview", dependencies=[Depends(require_user)])
    def mail_preview():
        return preview(db)

    @app.post("/api/mail/send", dependencies=[Depends(require_user)])
    def mail_send():
        result = send_digest(db)
        if result["status"] in ("blocked", "error"):
            raise HTTPException(400, result["message"])
        return result

    app.mount("/static", StaticFiles(directory=ROOT / "molt/static"), name="static")
    app.mount("/public-assets", StaticFiles(directory=ROOT / "molt/public/assets"), name="public-assets")
    return app

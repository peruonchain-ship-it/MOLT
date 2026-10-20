import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
OFFICIAL_BASE = "https://contratacionesabiertas.oece.gob.pe"
TIMEZONE = "America/Lima"
CITIES = ("Lima", "Cusco", "Trujillo", "Arequipa")
STAGES = ("Pendiente", "Revisar", "Cotizar", "Presentada", "Descartada")


@dataclass(frozen=True)
class Config:
    data_dir: Path
    secure_cookies: bool = False
    worker_enabled: bool = True
    mail_key: str = field(default="", repr=False)
    mail_from: str = ""
    mail_to: str = ""
    public_url: str = ""
    google_site_verification: str = ""
    database_url: str = field(default="", repr=False)
    initial_username: str = "propietario"
    initial_password: str = field(default="", repr=False)

    def __post_init__(self):
        if self.database_url:
            parsed = urlparse(self.database_url)
            if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
                raise ValueError("DATABASE_URL debe ser una conexión PostgreSQL válida.")
        if self.initial_password and not 12 <= len(self.initial_password) <= 200:
            raise ValueError("MOLT_INITIAL_PASSWORD debe tener entre 12 y 200 caracteres.")
        if not 1 <= len(self.initial_username) <= 80:
            raise ValueError("MOLT_INITIAL_USERNAME debe tener entre 1 y 80 caracteres.")
        if self.public_url:
            parsed = urlparse(self.public_url)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                    or parsed.port not in (None, 443)):
                raise ValueError("MOLT_PUBLIC_URL debe ser el origen HTTPS del dominio, sin rutas ni credenciales.")

    @classmethod
    def from_env(cls):
        path = Path(os.getenv("MOLT_DATA_DIR", str(ROOT / ".data"))).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        return cls(
            data_dir=path,
            secure_cookies=os.getenv("MOLT_SECURE_COOKIES", "false").lower() == "true",
            worker_enabled=os.getenv("MOLT_WORKER_ENABLED", "true").lower() == "true",
            mail_key=os.getenv("RESEND_API_KEY", ""),
            mail_from=os.getenv("MOLT_MAIL_FROM", ""),
            mail_to=os.getenv("MOLT_MAIL_TO", ""),
            public_url=os.getenv("MOLT_PUBLIC_URL", os.getenv("RENDER_EXTERNAL_URL", "")).strip().rstrip("/"),
            google_site_verification=os.getenv("MOLT_GOOGLE_SITE_VERIFICATION", "").strip(),
            database_url=os.getenv("DATABASE_URL", "").strip(),
            initial_username=os.getenv("MOLT_INITIAL_USERNAME", "propietario"),
            initial_password=os.getenv("MOLT_INITIAL_PASSWORD", ""),
        )

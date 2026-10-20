import os
from dataclasses import dataclass
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
    mail_key: str = ""
    mail_from: str = ""
    mail_to: str = ""
    public_url: str = ""
    google_site_verification: str = ""

    def __post_init__(self):
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
            public_url=os.getenv("MOLT_PUBLIC_URL", "").strip().rstrip("/"),
            google_site_verification=os.getenv("MOLT_GOOGLE_SITE_VERIFICATION", "").strip(),
        )

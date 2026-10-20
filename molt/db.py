import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime

import psycopg

from .config import CITIES, Config
from .postgres import Connection, connect

INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)


def utcnow():
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, config: Config):
        self.config = config
        config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        config.data_dir.chmod(0o700)
        self.path = config.data_dir / "molt.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_attempts (
                    key TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS opportunities (
                    ocid TEXT PRIMARY KEY, data TEXT NOT NULL, raw TEXT NOT NULL,
                    version TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                    changed_at TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'Pendiente',
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS documents (
                    key TEXT PRIMARY KEY, ocid TEXT NOT NULL, url TEXT NOT NULL,
                    title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    text TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
                    checked_at TEXT, attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS documents_queue ON documents(status, attempts);
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
                    status TEXT NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
                    scanned INTEGER NOT NULL DEFAULT 0, matched INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '', window_start TEXT, window_end TEXT,
                    next_url TEXT, source_latest TEXT
                );
                CREATE TABLE IF NOT EXISTS leases (name TEXT PRIMARY KEY, owner TEXT, until REAL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    recipient TEXT NOT NULL, ocid TEXT NOT NULL, version TEXT NOT NULL,
                    sent_at TEXT NOT NULL, PRIMARY KEY(recipient,ocid,version)
                );
                CREATE TABLE IF NOT EXISTS mail_runs (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
                    count INTEGER NOT NULL, message TEXT NOT NULL,
                    provider_id TEXT, scheduled_day TEXT
                );
                CREATE TABLE IF NOT EXISTS mail_outbox (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            defaults = {
                "cities": list(CITIES), "email_to": config.mail_to,
                "email_enabled": False, "digest_hour": 8, "digest_minute": 0,
                "include_historical": False, "lookback_days": 90,
                "scan_interval_hours": 6,
            }
            for key, value in defaults.items():
                db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO NOTHING", (key, json.dumps(value)))
        if not config.database_url:
            self.path.chmod(0o600)
        self.ensure_setup_code()

    @contextmanager
    def connect(self):
        conn = connect(self.config.database_url) if self.config.database_url else sqlite3.connect(self.path, timeout=30)
        if not self.config.database_url:
            conn.row_factory = sqlite3.Row
        try:
            yield Connection(conn) if self.config.database_url else conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_setup_code(self):
        if self.initialized():
            return
        path = self.config.data_dir / "setup-code"
        try:
            with open(path, "x", opener=lambda p, f: os.open(p, f, 0o600)) as f:
                f.write(secrets.token_urlsafe(24))
        except FileExistsError:
            pass

    def bootstrap_owner(self):
        if not self.config.initial_password or self.initialized():
            return
        from .auth import hash_password
        with self.connect() as db:
            db.execute("INSERT INTO users VALUES (1,?,?) ON CONFLICT(id) DO NOTHING",
                       (self.config.initial_username, hash_password(self.config.initial_password)))
        (self.config.data_dir / "setup-code").unlink(missing_ok=True)

    def city_expression(self, prefix=""):
        if prefix not in ("", "o."):
            raise ValueError("Invalid SQL prefix")
        return f"({prefix}data::jsonb->>'city')" if self.config.database_url else f"json_extract({prefix}data,'$.city')"

    def initialized(self):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM users").fetchone())

    def settings(self):
        with self.connect() as db:
            return {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")}

    def save_settings(self, settings):
        with self.connect() as db:
            for k, v in settings.items():
                db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (k, json.dumps(v)))

    def lease(self, name, seconds=1200):
        owner = secrets.token_hex(16)
        with self.connect() as db:
            now = time.time()
            row = db.execute("""INSERT INTO leases VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET
                owner=excluded.owner, until=excluded.until WHERE leases.until<=? RETURNING owner""",
                             (name, owner, now + seconds, now)).fetchone()
        return row[0] if row else None

    def renew(self, name, owner, seconds=1200):
        with self.connect() as db:
            db.execute("UPDATE leases SET until=? WHERE name=? AND owner=?",
                       (time.time() + seconds, name, owner))

    def release(self, name, owner):
        with self.connect() as db:
            db.execute("DELETE FROM leases WHERE name=? AND owner=?", (name, owner))

    def lease_active(self, name):
        with self.connect() as db:
            row = db.execute("SELECT until FROM leases WHERE name=?", (name,)).fetchone()
            return bool(row and row[0] > time.time())

    def sync_status(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            complete = db.execute(
                "SELECT finished_at FROM sync_runs WHERE status='complete' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            docs = {r[0]: r[1] for r in db.execute("SELECT status,COUNT(*) FROM documents GROUP BY status")}
        result = dict(row) if row else {"status": "never", "message": "Aún no se ha consultado la fuente."}
        result.pop("next_url", None)
        result["running"] = self.lease_active("sync")
        if result["status"] == "running" and not result["running"]:
            result["status"] = "interrupted"
            result["message"] = "La consulta se interrumpió. Se reanudará desde la última página guardada."
        result["last_complete"] = complete[0] if complete else None
        result["documents"] = docs
        config = self.settings()
        result["documents_paused"] = config.get("documents_paused", False)
        result["documents_message"] = config.get("documents_message", "")
        result["automation"] = {
            "web_worker": self.config.worker_enabled,
            "started": config.get("collector_started"), "finished": config.get("collector_finished"),
            "status": config.get("collector_status", "unconfigured"),
            "interval_hours": config["scan_interval_hours"],
        }
        return result

    def upsert(self, item, raw):
        data = json.dumps(item, ensure_ascii=False, sort_keys=True)
        meaningful = {k: v for k, v in item.items() if k not in (
            "source_updated", "classification", "status_reason", "document_checks")}
        version = hashlib.sha256(json.dumps(meaningful, sort_keys=True).encode()).hexdigest()
        now = utcnow()
        with self.connect() as db:
            db.execute("""
                INSERT INTO opportunities(ocid,data,raw,version,first_seen,last_seen,changed_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(ocid) DO UPDATE SET
                data=excluded.data,raw=excluded.raw,version=excluded.version,last_seen=excluded.last_seen,
                changed_at=CASE WHEN opportunities.version<>excluded.version
                    THEN excluded.changed_at ELSE opportunities.changed_at END
            """, (item["ocid"], data, json.dumps(raw, ensure_ascii=False), version, now, now, now))

    def queue_document(self, ocid, doc):
        # URL plus source publication/version date keeps changed attachments eligible for a new review.
        key = hashlib.sha256((ocid + doc["url"] + doc.get("date", "")).encode()).hexdigest()
        with self.connect() as db:
            db.execute("DELETE FROM documents WHERE ocid=? AND url=? AND key<>?", (ocid, doc["url"], key))
            unsupported = str(doc.get("format", "")).lower() in ("zip", "application/zip", "doc", "docx", "xls", "xlsx")
            status = "manual" if unsupported else "pending"
            detail = "Formato no PDF: requiere revisión manual del archivo oficial." if unsupported else ""
            db.execute("INSERT INTO documents(key,ocid,url,title,status,detail) VALUES (?,?,?,?,?,?) ON CONFLICT(key) DO NOTHING",
                       (key, ocid, doc["url"], doc.get("title", "Documento oficial"), status, detail))
            if unsupported:
                db.execute("UPDATE documents SET status='manual',detail=? WHERE key=? AND status IN ('pending','error')",
                           (detail, key))

    def opportunity(self, ocid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM opportunities WHERE ocid=?", (ocid,)).fetchone()
        return row

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from .config import CITIES, Config


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
                db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, json.dumps(value)))
        self.path.chmod(0o600)
        self.ensure_setup_code()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
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

    def initialized(self):
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM users").fetchone())

    def settings(self):
        with self.connect() as db:
            return {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM settings")}

    def save_settings(self, settings):
        with self.connect() as db:
            for k, v in settings.items():
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (k, json.dumps(v)))

    def lease(self, name, seconds=1200):
        owner = secrets.token_hex(16)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM leases WHERE name=?", (name,)).fetchone()
            if row and row["until"] > time.time():
                return None
            db.execute("INSERT OR REPLACE INTO leases VALUES (?,?,?)", (name, owner, time.time() + seconds))
        return owner

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
            db.execute("INSERT OR IGNORE INTO documents(key,ocid,url,title,status,detail) VALUES (?,?,?,?,?,?)",
                       (key, ocid, doc["url"], doc.get("title", "Documento oficial"), status, detail))
            if unsupported:
                db.execute("UPDATE documents SET status='manual',detail=? WHERE key=? AND status IN ('pending','error')",
                           (detail, key))

    def opportunity(self, ocid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM opportunities WHERE ocid=?", (ocid,)).fetchone()
        return row

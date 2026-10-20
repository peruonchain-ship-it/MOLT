import logging
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import TIMEZONE
from .db import utcnow
from .documents import process_documents
from .mail import send_digest
from .matching import parse_date
from .source import SyncService

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, db):
        self.db = db
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="molt-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)

    def tick(self):
        settings = self.db.settings()
        status = self.db.sync_status()
        now = datetime.now(ZoneInfo(TIMEZONE))
        last = parse_date(status.get("finished_at") or status.get("started_at"))
        # Refresh before the daily digest even when the regular 6-hour interval has not elapsed.
        digest_time = now.replace(hour=settings["digest_hour"], minute=settings["digest_minute"], second=0, microsecond=0)
        refresh_for_digest = (settings["email_enabled"] and now >= digest_time - timedelta(minutes=30)
                              and (not last or last < digest_time - timedelta(minutes=30)))
        retry_partial = status["status"] in ("partial", "interrupted")
        retry_error = status["status"] == "error" and (not last or now - last > timedelta(minutes=30))
        if not status["running"] and (not last or now - last > timedelta(hours=settings["scan_interval_hours"])
                                      or retry_partial or retry_error or refresh_for_digest):
            SyncService(self.db).run()
        if self.stop.is_set():
            return
        process_documents(self.db, limit=4)
        if settings["email_enabled"] and now >= digest_time:
            day = now.date().isoformat()
            with self.db.connect() as conn:
                row = conn.execute("SELECT * FROM mail_runs WHERE scheduled_day=? ORDER BY id DESC LIMIT 1", (day,)).fetchone()
            if row and row["status"] in ("sent", "empty"):
                return
            if row and parse_date(row["created_at"]) > now - timedelta(minutes=30):
                return
            result = send_digest(self.db, scheduled_day=day)
            if result["status"] == "blocked":
                with self.db.connect() as conn:
                    conn.execute("INSERT INTO mail_runs(created_at,status,count,message,scheduled_day) VALUES (?,?,?,?,?)",
                                 (now.isoformat(), "blocked", 0, result["message"], day))

    def loop(self):
        while not self.stop.is_set():
            try:
                # Reading data does not require an account; sending mail remains disabled until configured.
                self.tick()
            except Exception:
                log.exception("Fallo en tarea programada")
            self.stop.wait(60)


def collect_once(db):
    """One external scheduled run, independent of the web server's lifetime."""
    owner = db.lease("collector", seconds=3000)
    if not owner:
        return {"status": "busy"}
    try:
        db.save_settings({"collector_started": utcnow(), "collector_status": "running"})
        Worker(db).tick()
        failed = db.sync_status()["status"] in ("error", "partial", "interrupted")
        status = "error" if failed else "complete"
        db.save_settings({"collector_finished": utcnow(), "collector_status": status})
        return {"status": status}
    except Exception:
        # Connection errors must not expose deployment secrets in public workflow logs.
        db.save_settings({"collector_finished": utcnow(), "collector_status": "error"})
        return {"status": "error"}
    finally:
        db.release("collector", owner)

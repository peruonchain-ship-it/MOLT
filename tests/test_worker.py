from datetime import datetime
from zoneinfo import ZoneInfo

import molt.worker as module


def test_daily_digest_uses_peru_time_and_runs_once(db, monkeypatch):
    tz = ZoneInfo("America/Lima")

    class Clock(datetime):
        current = datetime(2026, 10, 19, 7, 59, tzinfo=tz)

        @classmethod
        def now(cls, zone=None):
            return cls.current.astimezone(zone) if zone else cls.current

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module, "process_documents", lambda *_args, **_kwargs: {"processed": 0})
    db.save_settings({"email_enabled": True, "digest_hour": 8, "digest_minute": 0})
    recent = datetime(2026, 10, 19, 7, 45, tzinfo=tz).isoformat()
    with db.connect() as conn:
        conn.execute("INSERT INTO sync_runs(started_at,finished_at,status) VALUES (?,?,'complete')", (recent, recent))
    sends = []

    def send(database, scheduled_day):
        sends.append(scheduled_day)
        with database.connect() as conn:
            conn.execute("INSERT INTO mail_runs(created_at,status,count,message,scheduled_day) VALUES (?,?,?,?,?)",
                         (Clock.current.isoformat(), "sent", 1, "Prueba", scheduled_day))
        return {"status": "sent"}

    monkeypatch.setattr(module, "send_digest", send)
    worker = module.Worker(db)
    worker.tick()
    assert sends == []
    Clock.current = datetime(2026, 10, 19, 8, 0, tzinfo=tz)
    worker.tick()
    assert sends == ["2026-10-19"]
    Clock.current = datetime(2026, 10, 19, 8, 1, tzinfo=tz)
    worker.tick()
    assert sends == ["2026-10-19"]

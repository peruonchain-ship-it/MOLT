from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import molt.postgres as postgres
import molt.worker as worker
from molt.app import create_app
from molt.db import Database, utcnow
from molt.source import save_release


def test_hosted_owner_and_records_survive_restart(config, release):
    hosted = replace(config, initial_password="test-private-initial-password")
    with TestClient(create_app(hosted)) as first:
        assert first.get("/api/auth/status").json()["initialized"] is True
        login = first.post("/api/auth/login", json={"username": "propietario", "password": hosted.initial_password})
        assert login.status_code == 200
        first.headers["X-CSRF-Token"] = login.json()["csrf"]
        save_release(first.app.state.db, release)
        assert first.patch("/api/opportunities/" + release["ocid"],
                           json={"stage": "Cotizar", "notes": "Nota privada persistente"}).status_code == 200
    # Changing the deployment's bootstrap password must never overwrite the existing owner.
    with TestClient(create_app(replace(hosted, initial_password="different-bootstrap-password"))) as second:
        assert second.get("/api/opportunities").status_code == 401
        assert second.post("/api/auth/login", json={"username": "propietario", "password": hosted.initial_password}).status_code == 200
        item = second.get("/api/opportunities").json()["items"][0]
        assert item["notes"] == "Nota privada persistente" and item["stage"] == "Cotizar"
    assert not (config.data_dir / "setup-code").exists()
    assert hosted.initial_password not in repr(hosted)


def test_lease_is_atomic_and_expired_owner_cannot_unlock_successor(db):
    with ThreadPoolExecutor(max_workers=4) as pool:
        owners = list(pool.map(lambda _: db.lease("simultaneous"), range(4)))
    winners = [owner for owner in owners if owner]
    assert len(winners) == 1
    with db.connect() as conn:
        conn.execute("UPDATE leases SET until=0 WHERE name='simultaneous'")
    successor = db.lease("simultaneous")
    assert successor and successor != winners[0]
    db.release("simultaneous", winners[0])
    assert db.lease("simultaneous") is None
    db.release("simultaneous", successor)
    assert db.lease("simultaneous")


def test_database_rolls_back_failed_transaction(config):
    db = Database(config)
    with pytest.raises(RuntimeError), db.connect() as conn:
        conn.execute("INSERT INTO settings VALUES ('rollback_probe','true')")
        raise RuntimeError("abort")
    assert "rollback_probe" not in Database(config).settings()


def test_external_collector_records_heartbeat_and_source_failure(db, monkeypatch):
    monkeypatch.setattr(worker.Worker, "tick", lambda _: None)
    assert worker.collect_once(db)["status"] == "complete"
    assert db.sync_status()["automation"]["status"] == "complete"
    with db.connect() as conn:
        conn.execute("INSERT INTO sync_runs(started_at,status) VALUES (?,'error')", (utcnow(),))
    assert worker.collect_once(db)["status"] == "error"
    assert db.sync_status()["automation"]["finished"]
    assert not db.lease_active("collector")


def test_cloud_database_checks_tls_identity(monkeypatch):
    calls = []
    monkeypatch.setattr(postgres.psycopg, "connect", lambda *args, **kwargs: calls.append(kwargs))
    postgres.connect("postgresql://owner:synthetic@example.com/db?sslmode=disable")
    assert calls[0]["sslmode"] == "verify-full"
    assert calls[0]["sslrootcert"] == postgres.certifi.where()


def test_short_initial_password_fails_before_startup(config):
    with pytest.raises(ValueError, match="MOLT_INITIAL_PASSWORD"):
        replace(config, initial_password="short")

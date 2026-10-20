from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from molt.app import create_app
from molt.config import Config
from molt.db import Database


@pytest.fixture
def config(tmp_path):
    return Config(data_dir=tmp_path / "private", worker_enabled=False, mail_to="owner@example.com")


@pytest.fixture
def db(config):
    return Database(config)


@pytest.fixture
def release():
    now = datetime.now(UTC)
    return {
        "ocid": "ocds-test-001", "date": now.isoformat(),
        "buyer": {"id": "buyer-1", "name": "Entidad de prueba"},
        "tender": {
            "title": "PROCESO-TEST-1", "description": "Servicio de organización y ejecución de evento institucional",
            "status": "active", "mainProcurementCategory": "services",
            "value": {"amount": 18000, "currency": "PEN"},
            "tenderPeriod": {"startDate": now.isoformat(), "endDate": (now + timedelta(days=10)).isoformat()},
            "items": [], "documents": [],
        },
        "parties": [{"id": "buyer-1", "name": "Entidad de prueba", "roles": ["buyer"],
                     "address": {"streetAddress": "Calle de prueba", "locality": "Miraflores",
                                 "region": "Lima", "department": "Lima"}}],
    }


@pytest.fixture
def client(config):
    with TestClient(create_app(config)) as client:
        yield client


@pytest.fixture
def owner(client, config):
    code = (config.data_dir / "setup-code").read_text().strip()
    response = client.post("/api/auth/setup", json={"username": "owner", "password": "private-test-password-123",
                                                   "code": code})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client


def text_pdf(text):
    """Small real PDF with selectable text; no external tool or network required."""
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 50 700 Td ({text}) Tj ET".encode("latin1")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    content = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        content += f"{offset:010d} 00000 n \n".encode()
    content += f"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n{xref}\n%%EOF".encode()
    return content

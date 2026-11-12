"""Tests for the FastAPI web backend."""

import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from incident_investigator.llm.provider import MockLLMProvider
from web.backend.main import app, investigations

TRIAGE_RESP = json.dumps(
    {
        "incident_window_start": "2024-01-15T10:25:00",
        "incident_window_end": "2024-01-15T10:35:00",
        "affected_services": ["db-proxy"],
        "primary_symptoms": ["Connection pool exhausted"],
        "anomalous_templates": [],
        "user_hint": "DB issue",
    }
)

GEN_RESP = json.dumps(
    [
        {
            "statement": "Database connection pool exhausted",
            "predicted_evidence": ["Error logs in db-proxy"],
            "falsification_conditions": ["Free connections available"],
        }
    ]
)

TEST_RESP = json.dumps(
    {
        "supports": True,
        "summary": "Verified connection pool exhaustion",
        "event_ids": ["evt_1"],
        "confidence": 0.85,
    }
)

CRITIC_RESP = json.dumps(
    {
        "verdict": "approved",
        "notes": "Verified temporal order",
    }
)

REPORT_RESP = json.dumps(
    {
        "executive_summary": "DB pool exhaustion caused outage",
        "root_cause": "Connection pool limit reached",
        "confidence": 0.85,
        "incident_timeline": [{"timestamp": "2024-01-15T10:28:00", "description": "Exhausted"}],
        "recommended_mitigations": ["Increase pool size"],
        "unknowns": [],
    }
)


def _get_mock_responses():
    return [TRIAGE_RESP, GEN_RESP, TEST_RESP, CRITIC_RESP, REPORT_RESP]


@pytest.fixture(autouse=True)
def setup_app_state():
    investigations.clear()
    app.state.llm = MockLLMProvider(responses=_get_mock_responses() * 5)
    yield
    investigations.clear()


def test_root_and_health():
    with TestClient(app) as client:
        r1 = client.get("/api/health")
        assert r1.status_code == 200
        assert r1.json() == {"status": "ok"}

        r2 = client.get("/")
        assert r2.status_code == 200


def test_get_investigations_empty():
    with TestClient(app) as client:
        r = client.get("/api/investigations")
        assert r.status_code == 200
        assert r.json() == []


def test_create_and_get_investigation_multipart():
    sample_log = (
        "2024-01-15 10:28:00.123 [ERROR] [db-proxy] Connection pool exhausted\n"
        "2024-01-15 10:29:00.123 [ERROR] [checkout-service] 504 Gateway Timeout\n"
    )

    with TestClient(app) as client:
        file_obj = io.BytesIO(sample_log.encode("utf-8"))
        files = [("files", ("test.log", file_obj, "text/plain"))]
        data = {"hint": "Check db-proxy"}

        resp = client.post("/api/investigations", files=files, data=data)
        assert resp.status_code == 200
        payload = resp.json()
        assert "id" in payload
        assert payload["status"] == "running"
        inv_id = payload["id"]

        # Wait for background investigation to finish
        for _ in range(50):
            r = client.get(f"/api/investigations/{inv_id}")
            assert r.status_code == 200
            rec = r.json()
            if rec["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        assert rec["status"] == "completed"
        assert rec["hint"] == "Check db-proxy"
        assert rec["result"] is not None
        assert rec["result"]["root_cause"] == "Connection pool limit reached"
        assert len(rec["events"]) > 0

        # Check list endpoint
        list_resp = client.get("/api/investigations")
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == inv_id
        assert items[0]["root_cause"] == "Connection pool limit reached"


def test_create_sample_investigation():
    with TestClient(app) as client:
        resp = client.post("/api/investigations/sample")
        assert resp.status_code == 200
        payload = resp.json()
        inv_id = payload["id"]
        assert payload["status"] == "running"

        # Wait for background task
        for _ in range(50):
            r = client.get(f"/api/investigations/{inv_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        rec = client.get(f"/api/investigations/{inv_id}").json()
        assert rec["status"] == "completed"
        assert "504" in rec["hint"]


def test_get_investigation_report_md_and_json():
    sample_log = "2024-01-15 10:28:00.123 [ERROR] [db-proxy] Connection pool exhausted\n"

    with TestClient(app) as client:
        file_obj = io.BytesIO(sample_log.encode("utf-8"))
        files = [("files", ("test.log", file_obj, "text/plain"))]

        resp = client.post("/api/investigations", files=files)
        inv_id = resp.json()["id"]

        for _ in range(50):
            r = client.get(f"/api/investigations/{inv_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        # Markdown report
        md_resp = client.get(f"/api/investigations/{inv_id}/report?format=md")
        assert md_resp.status_code == 200
        assert "Incident" in md_resp.text and "Report" in md_resp.text
        assert "DB pool exhaustion caused outage" in md_resp.text

        # JSON report
        json_resp = client.get(f"/api/investigations/{inv_id}/report?format=json")
        assert json_resp.status_code == 200
        data = json_resp.json()
        assert data["root_cause"] == "Connection pool limit reached"
        assert data["confidence"] == 0.85


def test_not_found_endpoints():
    with TestClient(app) as client:
        r1 = client.get("/api/investigations/nonexistent")
        assert r1.status_code == 404

        r2 = client.get("/api/investigations/nonexistent/report")
        assert r2.status_code == 404


def test_stream_events_replays_existing():
    with TestClient(app) as client:
        resp = client.post("/api/investigations/sample")
        inv_id = resp.json()["id"]

        for _ in range(50):
            r = client.get(f"/api/investigations/{inv_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)

        with client.stream("GET", f"/api/investigations/{inv_id}/events") as stream:
            lines = [line for line in stream.iter_lines() if line]
            assert len(lines) > 0
            assert any("data:" in l for l in lines)

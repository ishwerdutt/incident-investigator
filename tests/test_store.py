"""Tests for LogStore (DuckDB store)."""

from datetime import datetime

import pytest

from incident_investigator.models import BucketCount, LogEvent, LogLevel, TemplateCluster
from incident_investigator.store import LogStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_events() -> list[LogEvent]:
    """Realistic DB-timeout scenario across 3 services."""
    return [
        LogEvent(
            event_id="evt_001",
            timestamp=datetime(2024, 6, 15, 10, 0, 1),
            level=LogLevel.INFO,
            service="api-gateway",
            message="POST /checkout received",
            template_id="tpl_a",
            trace_id="trace_1",
            request_id="req_1",
            source_file="app.log",
            line_number=1,
            raw_line="2024-06-15 10:00:01 INFO POST /checkout received",
        ),
        LogEvent(
            event_id="evt_002",
            timestamp=datetime(2024, 6, 15, 10, 0, 2),
            level=LogLevel.INFO,
            service="checkout-service",
            message="Processing order for user 42",
            template_id="tpl_b",
            trace_id="trace_1",
            request_id="req_1",
            source_file="checkout.log",
            line_number=10,
            raw_line="2024-06-15 10:00:02 INFO Processing order for user 42",
        ),
        LogEvent(
            event_id="evt_003",
            timestamp=datetime(2024, 6, 15, 10, 0, 3),
            level=LogLevel.ERROR,
            service="db-proxy",
            message="Connection to db-primary timed out after 5000ms",
            template_id="tpl_c",
            trace_id="trace_1",
            request_id="req_1",
            source_file="dbproxy.log",
            line_number=55,
            raw_line="2024-06-15 10:00:03 ERROR Connection to db-primary timed out after 5000ms",
        ),
        LogEvent(
            event_id="evt_004",
            timestamp=datetime(2024, 6, 15, 10, 0, 4),
            level=LogLevel.ERROR,
            service="checkout-service",
            message="Failed to persist order: DB timeout",
            template_id="tpl_d",
            trace_id="trace_1",
            request_id="req_1",
            source_file="checkout.log",
            line_number=11,
            raw_line="2024-06-15 10:00:04 ERROR Failed to persist order: DB timeout",
        ),
        LogEvent(
            event_id="evt_005",
            timestamp=datetime(2024, 6, 15, 10, 0, 5),
            level=LogLevel.ERROR,
            service="api-gateway",
            message="502 Bad Gateway returned to client",
            template_id="tpl_e",
            trace_id="trace_1",
            request_id="req_1",
            source_file="app.log",
            line_number=2,
            raw_line="2024-06-15 10:00:05 ERROR 502 Bad Gateway returned to client",
        ),
        # Second request – normal path
        LogEvent(
            event_id="evt_006",
            timestamp=datetime(2024, 6, 15, 10, 1, 0),
            level=LogLevel.INFO,
            service="api-gateway",
            message="GET /status healthy",
            template_id="tpl_f",
            trace_id="trace_2",
            request_id="req_2",
            source_file="app.log",
            line_number=3,
            raw_line="2024-06-15 10:01:00 INFO GET /status healthy",
        ),
    ]


def _make_templates() -> list[TemplateCluster]:
    return [
        TemplateCluster(
            template_id="tpl_a",
            pattern="POST /checkout received",
            sample_message="POST /checkout received",
            total_count=1,
            first_seen=datetime(2024, 6, 15, 10, 0, 1),
            last_seen=datetime(2024, 6, 15, 10, 0, 1),
            services=["api-gateway"],
        ),
        TemplateCluster(
            template_id="tpl_c",
            pattern="Connection to <*> timed out after <*>ms",
            sample_message="Connection to db-primary timed out after 5000ms",
            total_count=1,
            first_seen=datetime(2024, 6, 15, 10, 0, 3),
            last_seen=datetime(2024, 6, 15, 10, 0, 3),
            services=["db-proxy"],
            is_anomaly=True,
            anomaly_score=4.2,
        ),
    ]


def _make_buckets() -> list[BucketCount]:
    return [
        BucketCount(
            template_id="tpl_c",
            bucket_start=datetime(2024, 6, 15, 10, 0, 0),
            bucket_minutes=1,
            count=1,
            level=LogLevel.ERROR,
            service="db-proxy",
        ),
        BucketCount(
            template_id="tpl_c",
            bucket_start=datetime(2024, 6, 15, 10, 1, 0),
            bucket_minutes=1,
            count=10,
            level=LogLevel.ERROR,
            service="db-proxy",
        ),
    ]


@pytest.fixture
def store() -> LogStore:
    s = LogStore()
    s.ingest_events(_make_events())
    s.ingest_templates(_make_templates())
    s.ingest_buckets(_make_buckets())
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestion:
    def test_events_ingested(self, store: LogStore):
        rows = store.query("SELECT COUNT(*) AS cnt FROM events")
        assert rows[0]["cnt"] == 6

    def test_templates_ingested(self, store: LogStore):
        rows = store.query("SELECT COUNT(*) AS cnt FROM templates")
        assert rows[0]["cnt"] == 2

    def test_buckets_ingested(self, store: LogStore):
        rows = store.query("SELECT COUNT(*) AS cnt FROM bucket_counts")
        assert rows[0]["cnt"] == 2


class TestRetrieval:
    def test_get_event_found(self, store: LogStore):
        evt = store.get_event("evt_003")
        assert evt is not None
        assert evt["service"] == "db-proxy"
        assert "timed out" in evt["message"]

    def test_get_event_not_found(self, store: LogStore):
        assert store.get_event("nonexistent") is None

    def test_arbitrary_query(self, store: LogStore):
        rows = store.query(
            "SELECT event_id FROM events WHERE level = ? ORDER BY event_id",
            ["ERROR"],
        )
        ids = [r["event_id"] for r in rows]
        assert ids == ["evt_003", "evt_004", "evt_005"]


class TestClose:
    def test_close(self):
        s = LogStore()
        s.close()  # should not raise

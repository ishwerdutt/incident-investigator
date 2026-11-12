"""Tests for InvestigationTools."""

from datetime import datetime

import pytest

from incident_investigator.models import BucketCount, LogEvent, LogLevel, TemplateCluster
from incident_investigator.store import LogStore
from incident_investigator.tools import InvestigationTools

# ---------------------------------------------------------------------------
# Realistic test data – DB timeout scenario
# ---------------------------------------------------------------------------


def _build_store() -> LogStore:
    store = LogStore()

    events = [
        # --- Normal window (09:50-09:59) ---
        LogEvent(
            event_id="evt_n1",
            timestamp=datetime(2024, 6, 15, 9, 50, 0),
            level=LogLevel.INFO,
            service="api-gateway",
            message="GET /health OK",
            template_id="tpl_health",
            trace_id="trace_n1",
            request_id="req_n1",
        ),
        LogEvent(
            event_id="evt_n2",
            timestamp=datetime(2024, 6, 15, 9, 55, 0),
            level=LogLevel.INFO,
            service="checkout-service",
            message="Order processed successfully",
            template_id="tpl_order_ok",
            trace_id="trace_n2",
            request_id="req_n2",
        ),
        # --- Incident window (10:00-10:05) ---
        # Request req_i1 – flows through 3 services
        LogEvent(
            event_id="evt_i1",
            timestamp=datetime(2024, 6, 15, 10, 0, 1),
            level=LogLevel.INFO,
            service="api-gateway",
            message="POST /checkout received",
            template_id="tpl_post",
            trace_id="trace_i1",
            request_id="req_i1",
        ),
        LogEvent(
            event_id="evt_i2",
            timestamp=datetime(2024, 6, 15, 10, 0, 2),
            level=LogLevel.INFO,
            service="checkout-service",
            message="Processing order for user 42",
            template_id="tpl_process",
            trace_id="trace_i1",
            request_id="req_i1",
        ),
        LogEvent(
            event_id="evt_i3",
            timestamp=datetime(2024, 6, 15, 10, 0, 3),
            level=LogLevel.ERROR,
            service="db-proxy",
            message="Connection to db-primary timed out after 5000ms",
            template_id="tpl_timeout",
            trace_id="trace_i1",
            request_id="req_i1",
        ),
        LogEvent(
            event_id="evt_i4",
            timestamp=datetime(2024, 6, 15, 10, 0, 5),
            level=LogLevel.ERROR,
            service="checkout-service",
            message="Failed to persist order: DB timeout",
            template_id="tpl_fail",
            trace_id="trace_i1",
            request_id="req_i1",
        ),
        LogEvent(
            event_id="evt_i5",
            timestamp=datetime(2024, 6, 15, 10, 0, 6),
            level=LogLevel.ERROR,
            service="api-gateway",
            message="502 Bad Gateway returned to client",
            template_id="tpl_502",
            trace_id="trace_i1",
            request_id="req_i1",
        ),
        # Second incident request
        LogEvent(
            event_id="evt_i6",
            timestamp=datetime(2024, 6, 15, 10, 1, 0),
            level=LogLevel.ERROR,
            service="db-proxy",
            message="Connection to db-primary timed out after 5000ms",
            template_id="tpl_timeout",
            trace_id="trace_i2",
            request_id="req_i2",
        ),
        LogEvent(
            event_id="evt_i7",
            timestamp=datetime(2024, 6, 15, 10, 1, 2),
            level=LogLevel.ERROR,
            service="checkout-service",
            message="Failed to persist order: DB timeout",
            template_id="tpl_fail",
            trace_id="trace_i2",
            request_id="req_i2",
        ),
        # A context-padding event
        LogEvent(
            event_id="evt_i8",
            timestamp=datetime(2024, 6, 15, 10, 0, 0),
            level=LogLevel.INFO,
            service="db-proxy",
            message="Health check OK",
            template_id="tpl_dbhealth",
        ),
        LogEvent(
            event_id="evt_i9",
            timestamp=datetime(2024, 6, 15, 10, 0, 10),
            level=LogLevel.INFO,
            service="db-proxy",
            message="Connection pool stats: 0 free",
            template_id="tpl_pool",
        ),
    ]

    templates = [
        TemplateCluster(
            template_id="tpl_health",
            pattern="GET /health OK",
            total_count=1,
            first_seen=datetime(2024, 6, 15, 9, 50, 0),
            last_seen=datetime(2024, 6, 15, 9, 50, 0),
            services=["api-gateway"],
        ),
        TemplateCluster(
            template_id="tpl_timeout",
            pattern="Connection to <*> timed out after <*>ms",
            sample_message="Connection to db-primary timed out after 5000ms",
            total_count=2,
            first_seen=datetime(2024, 6, 15, 10, 0, 3),
            last_seen=datetime(2024, 6, 15, 10, 1, 0),
            services=["db-proxy"],
            is_anomaly=True,
            anomaly_score=5.0,
        ),
        TemplateCluster(
            template_id="tpl_fail",
            pattern="Failed to persist order: DB timeout",
            total_count=2,
            first_seen=datetime(2024, 6, 15, 10, 0, 5),
            last_seen=datetime(2024, 6, 15, 10, 1, 2),
            services=["checkout-service"],
        ),
        TemplateCluster(
            template_id="tpl_order_ok",
            pattern="Order processed successfully",
            total_count=1,
            first_seen=datetime(2024, 6, 15, 9, 55, 0),
            last_seen=datetime(2024, 6, 15, 9, 55, 0),
            services=["checkout-service"],
        ),
    ]

    # Buckets: normal window has tpl_health, incident window has tpl_timeout spike
    buckets = [
        # Normal window
        BucketCount(
            template_id="tpl_health",
            bucket_start=datetime(2024, 6, 15, 9, 50, 0),
            count=1,
            level=LogLevel.INFO,
            service="api-gateway",
        ),
        BucketCount(
            template_id="tpl_order_ok",
            bucket_start=datetime(2024, 6, 15, 9, 55, 0),
            count=1,
            level=LogLevel.INFO,
            service="checkout-service",
        ),
        # Incident window
        BucketCount(
            template_id="tpl_timeout",
            bucket_start=datetime(2024, 6, 15, 10, 0, 0),
            count=1,
            level=LogLevel.ERROR,
            service="db-proxy",
        ),
        BucketCount(
            template_id="tpl_timeout",
            bucket_start=datetime(2024, 6, 15, 10, 1, 0),
            count=10,
            level=LogLevel.ERROR,
            service="db-proxy",
        ),
        BucketCount(
            template_id="tpl_fail",
            bucket_start=datetime(2024, 6, 15, 10, 0, 0),
            count=1,
            level=LogLevel.ERROR,
            service="checkout-service",
        ),
        BucketCount(
            template_id="tpl_fail",
            bucket_start=datetime(2024, 6, 15, 10, 1, 0),
            count=1,
            level=LogLevel.ERROR,
            service="checkout-service",
        ),
    ]

    store.ingest_events(events)
    store.ingest_templates(templates)
    store.ingest_buckets(buckets)
    return store


@pytest.fixture
def tools() -> InvestigationTools:
    return InvestigationTools(_build_store())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchLogs:
    def test_basic_search(self, tools: InvestigationTools):
        res = tools.search_logs("timed out")
        assert res["total_count"] == 2
        assert not res["truncated"]
        assert all("timed out" in r["message"] for r in res["results"])

    def test_search_with_service_filter(self, tools: InvestigationTools):
        res = tools.search_logs("timed out", service="db-proxy")
        assert res["total_count"] == 2

    def test_search_with_level_filter(self, tools: InvestigationTools):
        res = tools.search_logs("timed out", level="ERROR")
        assert res["total_count"] == 2

    def test_search_with_time_range(self, tools: InvestigationTools):
        res = tools.search_logs(
            "timed out",
            time_range=("2024-06-15 10:00:00", "2024-06-15 10:00:30"),
        )
        assert res["total_count"] == 1

    def test_truncation(self, tools: InvestigationTools):
        res = tools.search_logs("", limit=3)
        assert res["truncated"] is True
        assert len(res["results"]) == 3


class TestGetTemplateStats:
    def test_stats(self, tools: InvestigationTools):
        res = tools.get_template_stats("tpl_timeout")
        assert res["template_id"] == "tpl_timeout"
        assert res["pattern"] is not None
        assert res["total_count"] == 11  # 1 + 10
        assert res["spike_detected"] is True

    def test_no_spike(self, tools: InvestigationTools):
        res = tools.get_template_stats("tpl_fail")
        assert res["spike_detected"] is False


class TestGetContext:
    def test_context(self, tools: InvestigationTools):
        res = tools.get_context("evt_i3")  # db-proxy timeout at 10:00:03
        assert res["target"]["event_id"] == "evt_i3"
        # before: evt_i8 (10:00:00) is the only db-proxy event before
        assert len(res["before"]) >= 1
        # after: evt_i9 (10:00:10) and evt_i6 (10:01:00) in db-proxy
        assert len(res["after"]) >= 1

    def test_context_not_found(self, tools: InvestigationTools):
        res = tools.get_context("nonexistent")
        assert res["target"] is None


class TestTraceRequest:
    def test_trace(self, tools: InvestigationTools):
        res = tools.trace_request("req_i1")
        assert res["request_id"] == "req_i1"
        assert len(res["events"]) == 5
        assert set(res["services_involved"]) == {"api-gateway", "checkout-service", "db-proxy"}
        # Ensure ordering by timestamp
        timestamps = [e["timestamp"] for e in res["events"]]
        assert timestamps == sorted(timestamps)

    def test_trace_empty(self, tools: InvestigationTools):
        res = tools.trace_request("nonexistent")
        assert res["events"] == []


class TestCompareWindows:
    def test_compare(self, tools: InvestigationTools):
        res = tools.compare_windows(
            window_a=("2024-06-15 09:49:00", "2024-06-15 09:59:59"),
            window_b=("2024-06-15 10:00:00", "2024-06-15 10:05:00"),
        )
        # tpl_timeout and tpl_fail are new in window b
        new_ids = {e["template_id"] for e in res["new_in_b"]}
        assert "tpl_timeout" in new_ids
        assert "tpl_fail" in new_ids
        # tpl_health and tpl_order_ok disappeared in window b
        gone_ids = {e["template_id"] for e in res["disappeared"]}
        assert "tpl_health" in gone_ids
        assert "tpl_order_ok" in gone_ids


class TestFindFirstOccurrence:
    def test_first(self, tools: InvestigationTools):
        res = tools.find_first_occurrence("tpl_timeout")
        assert res["first_event"] is not None
        assert res["first_event"]["event_id"] == "evt_i3"
        assert res["total_occurrences"] == 2

    def test_first_no_match(self, tools: InvestigationTools):
        res = tools.find_first_occurrence("nonexistent")
        assert res["first_event"] is None
        assert res["total_occurrences"] == 0


class TestCorrelate:
    def test_correlation(self, tools: InvestigationTools):
        # tpl_timeout should precede tpl_fail
        res = tools.correlate("tpl_timeout", "tpl_fail", max_lag_seconds=10.0)
        assert res["correlation_found"] is True
        assert res["avg_lag_seconds"] > 0
        assert len(res["sample_pairs"]) >= 1

    def test_no_correlation(self, tools: InvestigationTools):
        res = tools.correlate("tpl_health", "tpl_timeout", max_lag_seconds=1.0)
        # Health at 9:50, timeout at 10:00 – lag > 1s threshold relative check
        # Actually they are 10 mins apart, well beyond 1s
        assert res["correlation_found"] is False


class TestGetServiceDependencies:
    def test_dependencies(self, tools: InvestigationTools):
        res = tools.get_service_dependencies()
        deps = res["dependencies"]
        assert len(deps) > 0
        # api-gateway → checkout-service should be present
        pairs = {(d["from"], d["to"]) for d in deps}
        assert ("api-gateway", "checkout-service") in pairs
        # checkout-service → db-proxy
        assert ("checkout-service", "db-proxy") in pairs

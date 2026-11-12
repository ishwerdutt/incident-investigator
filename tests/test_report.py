"""Tests for report rendering modules: MarkdownRenderer, JsonRenderer, HtmlRenderer."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from incident_investigator.models import (
    EvidenceItem,
    Hypothesis,
    HypothesisStatus,
    IncidentBrief,
    InvestigationResult,
)
from incident_investigator.report import (
    HtmlRenderer,
    JsonRenderer,
    MarkdownRenderer,
)


@pytest.fixture
def sample_brief() -> IncidentBrief:
    start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    end = datetime(2024, 1, 15, 10, 35, 0, tzinfo=UTC)
    return IncidentBrief(
        incident_window_start=start,
        incident_window_end=end,
        affected_services=["api-gateway", "checkout-service", "db-proxy"],
        primary_symptoms=["HTTP 504 Gateway Timeout", "Connection pool exhausted"],
        user_hint="Check db-proxy connection limits",
    )


@pytest.fixture
def sample_result(sample_brief: IncidentBrief) -> InvestigationResult:
    now = datetime(2024, 1, 15, 10, 15, 0, tzinfo=UTC)

    # Evidence for supported hypothesis
    ev1 = EvidenceItem(
        hypothesis_id="hyp_lead",
        event_ids=["evt_001", "evt_002"],
        summary="DB connection pool reached max capacity (100/100)",
        supports=True,
        tool_name="search_logs",
        tool_call_id="call_db_search",
        earliest_timestamp=now,
        latest_timestamp=now,
        explanation="db-proxy reported pool exhaustion repeatedly under peak load.",
    )
    ev2 = EvidenceItem(
        hypothesis_id="hyp_lead",
        event_ids=["evt_003"],
        summary="Cascading timeouts in upstream services",
        supports=True,
        tool_name="trace_request",
        tool_call_id="call_trace_01",
        earliest_timestamp=now,
        latest_timestamp=now,
        explanation="Trace demonstrates 30000ms delay waiting for free connection.",
    )

    supported_hyp = Hypothesis(
        id="hyp_lead",
        statement="Database connection pool exhaustion on db-proxy causing cascading gateway timeouts",
        predicted_evidence=["connection pool logs at max", "504 errors in checkout-service"],
        falsification_conditions=["available connections > 20% during peak"],
        status=HypothesisStatus.SUPPORTED,
        confidence=0.92,
        evidence=[ev1, ev2],
        tests_run=["test_db_pool_capacity", "test_upstream_latency"],
    )

    # Ruled out hypothesis
    ev_refute = EvidenceItem(
        hypothesis_id="hyp_net",
        event_ids=["evt_net_01"],
        summary="Network latency between host nodes normal (<1ms)",
        supports=False,
        tool_name="search_logs",
        explanation="Ping and TCP handshake timings did not show degradation.",
    )
    ruled_out_hyp = Hypothesis(
        id="hyp_net",
        statement="Physical network packet loss between availability zones",
        status=HypothesisStatus.REFUTED,
        confidence=0.10,
        evidence=[ev_refute],
        tests_run=["test_network_ping"],
        critic_notes="Refuted: intra-cluster ping roundtrip times were nominal (<1ms) throughout incident window.",
    )

    timeline = [
        {
            "timestamp": "2024-01-15T10:00:00Z",
            "service": "api-gateway",
            "description": "Traffic spike begins (2500 req/sec)",
        },
        {
            "timestamp": "2024-01-15T10:14:22Z",
            "service": "db-proxy",
            "description": "Connection pool saturated at 100 connections",
        },
        {
            "timestamp": "2024-01-15T10:15:05Z",
            "service": "checkout-service",
            "description": "HTTP 504 timeouts returned to clients",
        },
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "service": "db-proxy",
            "description": "Max connections bumped to 250, errors subside",
        },
    ]

    return InvestigationResult(
        incident_id="inc_20240115_dboutage",
        executive_summary="A database connection pool saturation on db-proxy caused widespread HTTP 504 timeouts across checkout-service.",
        root_cause="db-proxy connection pool exhaustion under sudden traffic surge",
        confidence=0.92,
        incident_timeline=timeline,
        supported_hypothesis=supported_hyp,
        ruled_out_hypotheses=[ruled_out_hyp],
        verified_evidence_event_ids=["evt_001", "evt_002", "evt_003"],
        recommended_mitigations=[
            "Increase db-proxy max connection pool size from 100 to 300",
            "Implement circuit breaker and fast-fail in checkout-service",
            "Add proactive alert at 80% pool utilization",
        ],
        unknowns=[
            "Exact marketing campaign source driving the 2.5x traffic surge",
        ],
        total_tokens_used=14850,
        total_tool_calls=12,
        investigation_duration_seconds=4.35,
        brief=sample_brief,
    )


# ---------------------------------------------------------------------------
# Test MarkdownRenderer
# ---------------------------------------------------------------------------


class TestMarkdownRenderer:
    def test_markdown_all_sections_populated(self, sample_result: InvestigationResult):
        renderer = MarkdownRenderer()
        md = renderer.render(sample_result)

        # Header & incident ID
        assert "# 🚨 Incident Investigation Report:" in md
        assert "inc_20240115_dboutage" in md

        # Executive summary & root cause
        assert "## 📋 Executive Summary" in md
        assert "database connection pool saturation" in md
        assert "## 🎯 Root Cause & Verdict" in md
        assert "db-proxy connection pool exhaustion" in md
        assert "92%" in md

        # Incident Brief
        assert "## ⏱️ Incident Brief" in md
        assert "api-gateway" in md
        assert "HTTP 504 Gateway Timeout" in md
        assert "Check db-proxy connection limits" in md

        # Timeline table
        assert "## 📅 Incident Timeline" in md
        assert "| Timestamp | Description | Service |" in md
        assert "Traffic spike begins" in md
        assert "db-proxy" in md

        # Supported hypothesis & evidence
        assert "## 🔬 Root-Cause Analysis (Supported Hypothesis)" in md
        assert "Database connection pool exhaustion on db-proxy" in md
        assert "#### 🧾 Evidence Trail" in md
        assert "evt_001" in md
        assert "evt_002" in md
        assert "call_db_search" in md
        assert "search_logs" in md

        # Verified citations summary
        assert "Verified Event Citations" in md

        # Ruled-out hypotheses
        assert "## ❌ Ruled-Out Hypotheses" in md
        assert "~~Physical network packet loss between availability zones~~" in md
        assert "Refuted: intra-cluster ping roundtrip times were nominal" in md

        # Mitigations & Unknowns
        assert "## 🛠️ Recommended Mitigations" in md
        assert "Increase db-proxy max connection pool size" in md
        assert "## ⚠️ Unknowns & Limitations" in md
        assert "Exact marketing campaign source" in md

        # Stats
        assert "### 📊 Execution Statistics" in md
        assert "14,850" in md
        assert "12" in md
        assert "4.35s" in md

    def test_markdown_empty_result(self):
        empty_result = InvestigationResult()
        md = empty_result.report_markdown()
        assert "# 🚨 Incident Investigation Report:" in md
        assert "*No timeline events recorded.*" in md
        assert "*No supported hypothesis recorded.*" in md
        assert "*No hypotheses were ruled out during this investigation.*" in md

    def test_markdown_via_model_method(self, sample_result: InvestigationResult):
        md = sample_result.report_markdown()
        assert "inc_20240115_dboutage" in md
        assert "## 📋 Executive Summary" in md


# ---------------------------------------------------------------------------
# Test JsonRenderer
# ---------------------------------------------------------------------------


class TestJsonRenderer:
    def test_json_rendering_and_roundtrip(self, sample_result: InvestigationResult):
        renderer = JsonRenderer()
        json_str = renderer.render(sample_result)

        # Valid JSON syntax
        parsed = json.loads(json_str)
        assert parsed["incident_id"] == "inc_20240115_dboutage"
        assert parsed["confidence"] == 0.92
        assert len(parsed["incident_timeline"]) == 4
        assert parsed["supported_hypothesis"]["statement"].startswith("Database connection pool")
        assert len(parsed["supported_hypothesis"]["evidence"]) == 2
        assert parsed["verified_evidence_event_ids"] == ["evt_001", "evt_002", "evt_003"]
        assert len(parsed["ruled_out_hypotheses"]) == 1

        # Roundtrip deserialization into Pydantic model
        restored = InvestigationResult.model_validate_json(json_str)
        assert restored.incident_id == sample_result.incident_id
        assert restored.root_cause == sample_result.root_cause
        assert restored.confidence == pytest.approx(sample_result.confidence)
        assert restored.supported_hypothesis is not None
        assert restored.supported_hypothesis.id == sample_result.supported_hypothesis.id
        assert len(restored.supported_hypothesis.evidence) == 2
        assert restored.supported_hypothesis.evidence[0].event_ids == ["evt_001", "evt_002"]
        assert restored.ruled_out_hypotheses[0].status == HypothesisStatus.REFUTED
        assert restored.total_tokens_used == 14850

    def test_json_to_dict(self, sample_result: InvestigationResult):
        renderer = JsonRenderer()
        data = renderer.to_dict(sample_result)
        assert isinstance(data, dict)
        assert data["incident_id"] == "inc_20240115_dboutage"
        assert isinstance(data["recommended_mitigations"], list)

    def test_json_via_model_method(self, sample_result: InvestigationResult):
        json_str = sample_result.report_json()
        restored = InvestigationResult.model_validate_json(json_str)
        assert restored.incident_id == sample_result.incident_id


# ---------------------------------------------------------------------------
# Test HtmlRenderer
# ---------------------------------------------------------------------------


class TestHtmlRenderer:
    def test_html_rendering_structure(self, sample_result: InvestigationResult):
        renderer = HtmlRenderer()
        report_html = renderer.render(sample_result)

        # Standard HTML5 structure
        assert report_html.strip().startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in report_html
        assert "<head>" in report_html
        assert "<body>" in report_html
        assert "</html>" in report_html

        # CSS styles and responsive dark/light support
        assert "<style>" in report_html
        assert "@media (prefers-color-scheme: dark)" in report_html
        assert "@media print" in report_html

        # SVG status icons embedded
        assert "<svg" in report_html
        assert 'class="icon' in report_html

        # Content elements
        assert "inc_20240115_dboutage" in report_html
        assert "db-proxy connection pool exhaustion" in report_html
        assert "92%" in report_html

    def test_html_evidence_tags_and_collapsible(self, sample_result: InvestigationResult):
        renderer = HtmlRenderer()
        report_html = renderer.render(sample_result)

        # Collapsible drawer for evidence
        assert '<details class="evidence-details' in report_html
        assert "<summary>" in report_html
        assert "Citations &amp; Details" in report_html

        # Badges for events and services
        assert '<span class="badge badge-event">evt_001</span>' in report_html
        assert '<span class="badge badge-event">evt_002</span>' in report_html
        assert '<span class="badge badge-service">api-gateway</span>' in report_html
        assert '<span class="badge badge-tool">search_logs</span>' in report_html

        # Ruled-out hypotheses section
        assert "<s>Physical network packet loss" in report_html
        assert "REFUTED" in report_html

        # Mitigations and stats
        assert "Increase db-proxy max connection pool size" in report_html
        assert "14,850" in report_html
        assert "4.35s" in report_html

    def test_html_escaping(self):
        """Ensure potential XSS or raw special chars are properly escaped in HTML."""
        dangerous_result = InvestigationResult(
            incident_id="inc_xss<script>alert(1)</script>",
            executive_summary='Summary with <bad> tags & "quotes"',
            root_cause="Root cause <injection>",
        )
        report_html = HtmlRenderer().render(dangerous_result)
        assert "<script>alert(1)</script>" not in report_html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report_html
        assert "&lt;bad&gt; tags &amp; &quot;quotes&quot;" in report_html
        assert "&lt;injection&gt;" in report_html

    def test_html_via_model_method(self, sample_result: InvestigationResult):
        report_html = sample_result.report_html()
        assert "<!DOCTYPE html>" in report_html
        assert "inc_20240115_dboutage" in report_html

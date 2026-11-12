"""Tests for the preprocessing modules: redactor, drain, analyzer."""

from __future__ import annotations

from datetime import datetime, timedelta

from incident_investigator.models import BucketCount, LogEvent, LogLevel, TemplateCluster
from incident_investigator.preprocess.analyzer import LogAnalyzer
from incident_investigator.preprocess.drain import TemplateExtractor
from incident_investigator.preprocess.redactor import Redactor

# ---------------------------------------------------------------------------
# Redactor
# ---------------------------------------------------------------------------


class TestRedactor:
    def setup_method(self):
        self.r = Redactor()

    def test_email(self):
        assert "<REDACTED_EMAIL>" in self.r.redact("user admin@example.com logged in")

    def test_ipv4(self):
        assert "<REDACTED_IP>" in self.r.redact("Connection from 192.168.1.1 refused")

    def test_ipv6(self):
        result = self.r.redact("Host 2001:0db8:85a3:0000:0000:8a2e:0370:7334 connected")
        assert "<REDACTED_IPV6>" in result

    def test_bearer_token(self):
        result = self.r.redact(
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc"
        )
        assert "<REDACTED_TOKEN>" in result
        assert "eyJ" not in result

    def test_aws_key(self):
        result = self.r.redact("Using key AKIAIOSFODNN7EXAMPLE")
        assert "<REDACTED_KEY>" in result

    def test_sk_key(self):
        result = self.r.redact("api_key=sk-proj-abcdefghijklmnopqrstuvwxyz")
        assert "<REDACTED_KEY>" in result

    def test_hex_key_after_key_eq(self):
        hex_key = "a" * 40
        result = self.r.redact(f"key={hex_key}")
        assert "<REDACTED_KEY>" in result
        assert hex_key not in result

    def test_no_false_positive_on_normal_text(self):
        text = "The quick brown fox jumps over the lazy dog"
        assert self.r.redact(text) == text


# ---------------------------------------------------------------------------
# TemplateExtractor (Drain3)
# ---------------------------------------------------------------------------


class TestTemplateExtractor:
    def test_clusters_similar_messages(self):
        te = TemplateExtractor()
        for i in range(5):
            te.add_log_message(f"Connection to host-{i}.example.com timed out after {100 + i}ms")
        for i in range(5):
            te.add_log_message(f"User user-{i} logged in successfully")

        templates = te.get_templates()
        assert len(templates) >= 2, f"Expected at least 2 clusters, got {len(templates)}"
        # Each should be a TemplateCluster model
        assert all(isinstance(t, TemplateCluster) for t in templates)

    def test_add_log_message_returns_id(self):
        te = TemplateExtractor()
        cid = te.add_log_message("Server started on port 8080")
        assert isinstance(cid, str)
        assert len(cid) > 0


# ---------------------------------------------------------------------------
# LogAnalyzer
# ---------------------------------------------------------------------------


class TestLogAnalyzer:
    def _make_events(self, template_id: str, count: int, start: datetime, interval_seconds: int = 30) -> list[LogEvent]:
        events = []
        for i in range(count):
            events.append(
                LogEvent(
                    timestamp=start + timedelta(seconds=i * interval_seconds),
                    level=LogLevel.ERROR,
                    message=f"msg {i}",
                    template_id=template_id,
                    service="svc",
                )
            )
        return events

    def test_bucket_events(self):
        start = datetime(2024, 1, 15, 10, 0, 0)
        events = self._make_events("t1", 10, start, interval_seconds=10)
        buckets = LogAnalyzer.bucket_events(events, bucket_minutes=1)
        assert len(buckets) >= 1
        total = sum(b.count for b in buckets)
        assert total == 10

    def test_score_anomalies_flags_spike(self):
        """A template with a spike bucket should be flagged as anomaly."""
        start = datetime(2024, 1, 15, 10, 0, 0)
        # Normal: 2 events per minute for 10 minutes
        events = self._make_events("t1", 20, start, interval_seconds=30)
        # Spike: 50 events in minute 11
        spike_start = start + timedelta(minutes=10)
        events.extend(self._make_events("t1", 50, spike_start, interval_seconds=1))

        buckets = LogAnalyzer.bucket_events(events, bucket_minutes=1)
        tpl = TemplateCluster(template_id="t1", pattern="msg <*>", total_count=70)
        scored = LogAnalyzer.score_anomalies([tpl], buckets, z_threshold=2.0)
        assert len(scored) == 1
        assert scored[0].is_anomaly is True
        assert scored[0].anomaly_score >= 2.0

    def test_score_anomalies_new_template(self):
        """A template first_seen in the last 10% of time range should be flagged."""
        start = datetime(2024, 1, 15, 10, 0, 0)
        end = start + timedelta(minutes=100)
        first_seen = end - timedelta(minutes=5)  # within last 10%

        tpl = TemplateCluster(template_id="t2", pattern="new stuff", total_count=3, first_seen=first_seen)
        # Only a few buckets
        buckets = [
            BucketCount(template_id="t2", bucket_start=first_seen, count=3),
        ]
        # Need at least one other bucket to establish time range
        buckets.append(BucketCount(template_id="other", bucket_start=start, count=1))
        scored = LogAnalyzer.score_anomalies([tpl], buckets, z_threshold=3.0)
        anomalous = [t for t in scored if t.is_anomaly]
        assert len(anomalous) >= 1
        assert anomalous[0].template_id == "t2"

    def test_score_anomalies_sorted_desc(self):
        tpl1 = TemplateCluster(template_id="t1", pattern="p1", anomaly_score=1.0)
        tpl2 = TemplateCluster(template_id="t2", pattern="p2", anomaly_score=5.0)
        scored = LogAnalyzer.score_anomalies([tpl1, tpl2], [], z_threshold=3.0)
        assert scored[0].template_id == "t2"

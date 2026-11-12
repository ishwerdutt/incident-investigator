"""Tests for the ingestion parsers."""

from __future__ import annotations

import json

from incident_investigator.ingest.parsers import (
    AutoParser,
    JsonLogParser,
    LogParser,
    RegexLogParser,
)
from incident_investigator.models import LogLevel

# ---------------------------------------------------------------------------
# JsonLogParser
# ---------------------------------------------------------------------------


class TestJsonLogParser:
    def test_parse_basic(self):
        parser = JsonLogParser()
        line = json.dumps(
            {
                "timestamp": "2024-01-15T10:30:45.123",
                "level": "ERROR",
                "service": "auth",
                "message": "Login failed",
                "trace_id": "abc123",
                "request_id": "req-1",
            }
        )
        ev = parser.parse_line(line, "app.log", 1)
        assert ev is not None
        assert ev.level == LogLevel.ERROR
        assert ev.service == "auth"
        assert ev.message == "Login failed"
        assert ev.trace_id == "abc123"
        assert ev.request_id == "req-1"
        assert ev.source_file == "app.log"
        assert ev.line_number == 1

    def test_alternative_keys(self):
        parser = JsonLogParser()
        line = json.dumps(
            {
                "ts": "2024-01-15T10:30:45",
                "severity": "WARN",
                "app": "billing",
                "msg": "Timeout",
                "traceId": "t1",
                "requestId": "r1",
            }
        )
        ev = parser.parse_line(line, "app.log", 2)
        assert ev is not None
        assert ev.level == LogLevel.WARN
        assert ev.service == "billing"
        assert ev.message == "Timeout"
        assert ev.trace_id == "t1"
        assert ev.request_id == "r1"

    def test_returns_none_for_non_json(self):
        parser = JsonLogParser()
        assert parser.parse_line("not json at all", "f", 0) is None

    def test_returns_none_for_empty(self):
        parser = JsonLogParser()
        assert parser.parse_line("", "f", 0) is None

    def test_returns_none_for_missing_timestamp(self):
        parser = JsonLogParser()
        line = json.dumps({"level": "INFO", "message": "hi"})
        assert parser.parse_line(line, "f", 0) is None


# ---------------------------------------------------------------------------
# RegexLogParser
# ---------------------------------------------------------------------------


class TestRegexLogParser:
    def test_iso_format(self):
        parser = RegexLogParser()
        line = "2024-01-15 10:30:45.123 [ERROR] [auth-service] Connection refused"
        ev = parser.parse_line(line, "app.log", 5)
        assert ev is not None
        assert ev.level == LogLevel.ERROR
        assert ev.service == "auth-service"
        assert ev.message == "Connection refused"

    def test_simple_format(self):
        parser = RegexLogParser()
        line = "[2024-01-15T10:30:45] ERROR something went wrong"
        ev = parser.parse_line(line, "f", 1)
        assert ev is not None
        assert ev.level == LogLevel.ERROR
        assert ev.message == "something went wrong"

    def test_syslog_format(self):
        parser = RegexLogParser()
        line = "Jan 15 10:30:45 webhost nginx[1234]: GET /index.html 200"
        ev = parser.parse_line(line, "syslog", 3)
        assert ev is not None
        assert ev.service == "nginx"
        assert "GET /index.html" in ev.message

    def test_returns_none_for_garbage(self):
        parser = RegexLogParser()
        assert parser.parse_line("~~~random garbage~~~", "f", 0) is None

    def test_returns_none_for_empty(self):
        parser = RegexLogParser()
        assert parser.parse_line("   ", "f", 0) is None


# ---------------------------------------------------------------------------
# AutoParser
# ---------------------------------------------------------------------------


class TestAutoParser:
    def test_detects_json(self):
        lines = [
            json.dumps({"timestamp": "2024-01-15T10:30:45", "level": "INFO", "message": f"msg {i}"}) for i in range(10)
        ]
        parser = AutoParser(lines)
        ev = parser.parse_line(lines[0], "f", 0)
        assert ev is not None
        assert ev.message == "msg 0"

    def test_detects_regex(self):
        lines = [f"2024-01-15 10:30:{i:02d}.000 [INFO] [svc] message {i}" for i in range(10)]
        parser = AutoParser(lines)
        ev = parser.parse_line(lines[0], "f", 0)
        assert ev is not None
        assert ev.service == "svc"

    def test_protocol(self):
        assert isinstance(JsonLogParser(), LogParser)
        assert isinstance(RegexLogParser(), LogParser)

"""Log line parsers: JSON, Regex and Auto-detecting."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Protocol, runtime_checkable

from incident_investigator.models import LogEvent, LogLevel

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LogParser(Protocol):
    """Minimal interface every log parser must satisfy."""

    def parse_line(self, line: str, source_file: str, line_number: int) -> LogEvent | None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEVEL_MAP: dict[str, LogLevel] = {
    "debug": LogLevel.DEBUG,
    "info": LogLevel.INFO,
    "information": LogLevel.INFO,
    "warn": LogLevel.WARN,
    "warning": LogLevel.WARN,
    "error": LogLevel.ERROR,
    "err": LogLevel.ERROR,
    "fatal": LogLevel.FATAL,
    "critical": LogLevel.FATAL,
    "crit": LogLevel.FATAL,
}


def _normalise_level(raw: str | None) -> LogLevel:
    if raw is None:
        return LogLevel.UNKNOWN
    return _LEVEL_MAP.get(raw.strip().lower(), LogLevel.UNKNOWN)


def _first_present(data: dict, *keys: str) -> str | None:
    """Return the value of the first key found in *data*, or None."""
    for k in keys:
        if k in data and data[k] is not None:
            return str(data[k])
    return None


def _parse_timestamp(raw: str) -> datetime:
    """Best-effort timestamp parsing."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {raw!r}")


# ---------------------------------------------------------------------------
# JSON parser
# ---------------------------------------------------------------------------


class JsonLogParser:
    """Parses structured JSON log lines."""

    def parse_line(self, line: str, source_file: str, line_number: int) -> LogEvent | None:
        line = line.strip()
        if not line:
            return None
        try:
            data: dict = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None

        ts_raw = _first_present(data, "timestamp", "ts", "time", "@timestamp")
        if ts_raw is None:
            return None
        try:
            ts = _parse_timestamp(ts_raw)
        except ValueError:
            return None

        level_raw = _first_present(data, "level", "severity", "log.level")
        service = _first_present(data, "service", "app", "application", "service.name") or "unknown"
        message = _first_present(data, "message", "msg", "log") or ""
        trace_id = _first_present(data, "trace_id", "traceId", "trace.id")
        request_id = _first_present(data, "request_id", "requestId")

        return LogEvent(
            timestamp=ts,
            level=_normalise_level(level_raw),
            service=service,
            message=message,
            trace_id=trace_id,
            request_id=request_id,
            source_file=source_file,
            line_number=line_number,
            raw_line=line,
        )


# ---------------------------------------------------------------------------
# Regex parser
# ---------------------------------------------------------------------------

# ISO:    2024-01-15 10:30:45.123 [ERROR] [service-name] Message here
_RE_ISO = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"\[(?P<level>\w+)\]\s+"
    r"\[(?P<service>[^\]]+)\]\s+"
    r"(?P<message>.+)$"
)

# Simple: [2024-01-15T10:30:45] ERROR message
_RE_SIMPLE = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<message>.+)$"
)

# Syslog: Jan 15 10:30:45 hostname service[pid]: message
_RE_SYSLOG = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<service>[^\[:]+)(?:\[(?P<pid>\d+)\])?:\s+"
    r"(?P<message>.+)$"
)


def _parse_syslog_ts(raw: str) -> datetime:
    now = datetime.now(tz=None)
    ts = datetime.strptime(raw, "%b %d %H:%M:%S")
    return ts.replace(year=now.year)


class RegexLogParser:
    """Handles common unstructured log formats via regex patterns."""

    def parse_line(self, line: str, source_file: str, line_number: int) -> LogEvent | None:
        line_stripped = line.strip()
        if not line_stripped:
            return None

        # Try ISO format
        m = _RE_ISO.match(line_stripped)
        if m:
            return LogEvent(
                timestamp=_parse_timestamp(m.group("ts")),
                level=_normalise_level(m.group("level")),
                service=m.group("service"),
                message=m.group("message"),
                source_file=source_file,
                line_number=line_number,
                raw_line=line_stripped,
            )

        # Try Simple format
        m = _RE_SIMPLE.match(line_stripped)
        if m:
            return LogEvent(
                timestamp=_parse_timestamp(m.group("ts")),
                level=_normalise_level(m.group("level")),
                message=m.group("message"),
                source_file=source_file,
                line_number=line_number,
                raw_line=line_stripped,
            )

        # Try Syslog format
        m = _RE_SYSLOG.match(line_stripped)
        if m:
            return LogEvent(
                timestamp=_parse_syslog_ts(m.group("ts")),
                level=LogLevel.UNKNOWN,
                service=m.group("service").strip(),
                message=m.group("message"),
                source_file=source_file,
                line_number=line_number,
                raw_line=line_stripped,
            )

        return None


# ---------------------------------------------------------------------------
# Auto-detecting parser
# ---------------------------------------------------------------------------


class AutoParser:
    """Samples lines to decide between JSON and Regex parsing, then delegates."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self._delegate: LogParser | None = None
        if lines is not None:
            self._detect(lines)

    def _detect(self, lines: list[str]) -> None:
        non_empty = [l for l in lines if l.strip()][:20]
        if not non_empty:
            self._delegate = RegexLogParser()
            return
        json_parser = JsonLogParser()
        json_count = sum(1 for l in non_empty if json_parser.parse_line(l, "", 0) is not None)
        self._delegate = JsonLogParser() if json_count > len(non_empty) / 2 else RegexLogParser()

    def parse_line(self, line: str, source_file: str, line_number: int) -> LogEvent | None:
        if self._delegate is None:
            self._detect([line])
        return self._delegate.parse_line(line, source_file, line_number)

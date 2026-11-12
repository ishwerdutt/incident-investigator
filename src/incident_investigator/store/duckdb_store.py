"""DuckDB-backed log store for the incident investigator."""

from __future__ import annotations

import json
from typing import Any

import duckdb

from incident_investigator.models import BucketCount, LogEvent, TemplateCluster

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR PRIMARY KEY,
    timestamp TIMESTAMP,
    level VARCHAR,
    service VARCHAR,
    message TEXT,
    template_id VARCHAR,
    trace_id VARCHAR,
    request_id VARCHAR,
    source_file VARCHAR,
    line_number INTEGER,
    raw_line TEXT
);
"""

_CREATE_TEMPLATES = """
CREATE TABLE IF NOT EXISTS templates (
    template_id VARCHAR PRIMARY KEY,
    pattern TEXT,
    sample_message TEXT,
    total_count INTEGER,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    services TEXT,
    is_anomaly BOOLEAN,
    anomaly_score DOUBLE
);
"""

_CREATE_BUCKETS = """
CREATE TABLE IF NOT EXISTS bucket_counts (
    template_id VARCHAR,
    bucket_start TIMESTAMP,
    bucket_minutes INTEGER,
    count INTEGER,
    level VARCHAR,
    service VARCHAR
);
"""


class LogStore:
    """Thin wrapper around a DuckDB database holding log events, templates,
    and time-bucket counts."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.con = duckdb.connect(db_path)
        self.con.execute(_CREATE_EVENTS)
        self.con.execute(_CREATE_TEMPLATES)
        self.con.execute(_CREATE_BUCKETS)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_events(self, events: list[LogEvent]) -> None:
        """Bulk insert LogEvents into the events table."""
        if not events:
            return
        rows = [
            (
                e.event_id,
                e.timestamp,
                e.level.value,
                e.service,
                e.message,
                e.template_id,
                e.trace_id,
                e.request_id,
                e.source_file,
                e.line_number,
                e.raw_line,
            )
            for e in events
        ]
        self.con.executemany(
            "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )

    def ingest_templates(self, templates: list[TemplateCluster]) -> None:
        """Insert TemplateClusters into the templates table."""
        if not templates:
            return
        rows = [
            (
                t.template_id,
                t.pattern,
                t.sample_message,
                t.total_count,
                t.first_seen,
                t.last_seen,
                json.dumps(t.services),
                t.is_anomaly,
                t.anomaly_score,
            )
            for t in templates
        ]
        self.con.executemany(
            "INSERT OR REPLACE INTO templates VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )

    def ingest_buckets(self, buckets: list[BucketCount]) -> None:
        """Insert BucketCounts into the bucket_counts table."""
        if not buckets:
            return
        rows = [
            (
                b.template_id,
                b.bucket_start,
                b.bucket_minutes,
                b.count,
                b.level.value,
                b.service,
            )
            for b in buckets
        ]
        self.con.executemany(
            "INSERT INTO bucket_counts VALUES (?,?,?,?,?,?)",
            rows,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Fetch a single event by its ID."""
        result = self.con.execute("SELECT * FROM events WHERE event_id = ?", [event_id])
        cols = [desc[0] for desc in result.description]
        row = result.fetchone()
        if row is None:
            return None
        return dict(zip(cols, row))

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Execute an arbitrary read query and return a list of dicts."""
        result = self.con.execute(sql, params or [])
        cols = [desc[0] for desc in result.description]
        return [dict(zip(cols, row)) for row in result.fetchall()]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the DuckDB connection."""
        self.con.close()

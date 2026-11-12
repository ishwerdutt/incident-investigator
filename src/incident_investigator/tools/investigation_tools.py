"""Eight bounded investigation tools backed by a LogStore."""

from __future__ import annotations

from typing import Any

from incident_investigator.store.duckdb_store import LogStore


class InvestigationTools:
    """Investigation tools that query a :class:`LogStore`.

    Every public method returns a dict with bounded results and always
    includes ``event_id`` references where applicable.
    """

    def __init__(self, store: LogStore) -> None:
        self.store = store

    # ------------------------------------------------------------------
    # 1. search_logs
    # ------------------------------------------------------------------

    def search_logs(
        self,
        query: str,
        time_range: tuple[str, str] | None = None,
        service: str | None = None,
        level: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """SQL LIKE search on message with optional filters."""
        clauses: list[str] = ["message LIKE ?"]
        params: list[Any] = [f"%{query}%"]

        if time_range:
            clauses.append("timestamp BETWEEN ? AND ?")
            params.extend(time_range)
        if service:
            clauses.append("service = ?")
            params.append(service)
        if level:
            clauses.append("level = ?")
            params.append(level)

        where = " AND ".join(clauses)

        # Total count
        total_row = self.store.query(f"SELECT COUNT(*) AS cnt FROM events WHERE {where}", params)
        total_count = total_row[0]["cnt"] if total_row else 0

        rows = self.store.query(
            f"SELECT * FROM events WHERE {where} ORDER BY timestamp LIMIT ?",
            params + [limit],
        )

        return {
            "results": rows,
            "total_count": total_count,
            "truncated": total_count > limit,
        }

    # ------------------------------------------------------------------
    # 2. get_template_stats
    # ------------------------------------------------------------------

    def get_template_stats(
        self,
        template_id: str,
        time_range: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Bucket counts and spike detection for a template."""
        # Get the template pattern and anomaly flag
        tpl_rows = self.store.query(
            "SELECT pattern, is_anomaly FROM templates WHERE template_id = ?",
            [template_id],
        )
        pattern = tpl_rows[0]["pattern"] if tpl_rows else None
        is_tpl_anomaly = (
            bool(tpl_rows[0]["is_anomaly"]) if tpl_rows and tpl_rows[0].get("is_anomaly") is not None else False
        )

        clauses = ["template_id = ?"]
        params: list[Any] = [template_id]
        if time_range:
            clauses.append("bucket_start BETWEEN ? AND ?")
            params.extend(time_range)

        where = " AND ".join(clauses)
        buckets = self.store.query(
            f"SELECT * FROM bucket_counts WHERE {where} ORDER BY bucket_start",
            params,
        )

        total_count = sum(b["count"] for b in buckets)

        # Spike detection: flagged as anomaly in templates, or significant bucket spike
        spike_detected = is_tpl_anomaly
        if not spike_detected and buckets:
            counts = [b["count"] for b in buckets]
            if len(counts) >= 2:
                min_c = min(counts)
                max_c = max(counts)
                mean = total_count / len(counts)
                if (
                    min_c > 0
                    and max_c >= 3 * min_c
                    or min_c == 0
                    and max_c > 0
                    or len(counts) > 2
                    and mean > 0
                    and any(c > 2 * mean for c in counts)
                ):
                    spike_detected = True

        return {
            "template_id": template_id,
            "pattern": pattern,
            "buckets": buckets,
            "total_count": total_count,
            "spike_detected": spike_detected,
        }

    # ------------------------------------------------------------------
    # 3. get_context
    # ------------------------------------------------------------------

    def get_context(
        self,
        event_id: str,
        before: int = 5,
        after: int = 5,
    ) -> dict[str, Any]:
        """Get surrounding events by timestamp in the same service."""
        target = self.store.get_event(event_id)
        if target is None:
            return {"target": None, "before": [], "after": []}

        ts = target["timestamp"]
        svc = target["service"]

        before_rows = self.store.query(
            "SELECT * FROM events WHERE service = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT ?",
            [svc, ts, before],
        )
        before_rows.reverse()

        after_rows = self.store.query(
            "SELECT * FROM events WHERE service = ? AND timestamp > ? ORDER BY timestamp ASC LIMIT ?",
            [svc, ts, after],
        )

        return {"target": target, "before": before_rows, "after": after_rows}

    # ------------------------------------------------------------------
    # 4. trace_request
    # ------------------------------------------------------------------

    def trace_request(self, request_id: str) -> dict[str, Any]:
        """All events sharing a request_id, ordered by timestamp."""
        rows = self.store.query(
            "SELECT * FROM events WHERE request_id = ? ORDER BY timestamp",
            [request_id],
        )
        services = sorted({r["service"] for r in rows})
        return {
            "request_id": request_id,
            "events": rows,
            "services_involved": services,
        }

    # ------------------------------------------------------------------
    # 5. compare_windows
    # ------------------------------------------------------------------

    def compare_windows(
        self,
        window_a: tuple[str, str],
        window_b: tuple[str, str],
    ) -> dict[str, Any]:
        """Compare template counts between two time windows."""

        def _template_counts(window: tuple[str, str]) -> dict[str, int]:
            rows = self.store.query(
                "SELECT template_id, SUM(count) AS total "
                "FROM bucket_counts "
                "WHERE bucket_start BETWEEN ? AND ? "
                "GROUP BY template_id",
                list(window),
            )
            return {r["template_id"]: int(r["total"]) for r in rows}

        counts_a = _template_counts(window_a)
        counts_b = _template_counts(window_b)

        all_ids = set(counts_a) | set(counts_b)

        new_in_b: list[dict[str, Any]] = []
        disappeared: list[dict[str, Any]] = []
        increased: list[dict[str, Any]] = []
        decreased: list[dict[str, Any]] = []

        for tid in all_ids:
            ca = counts_a.get(tid, 0)
            cb = counts_b.get(tid, 0)
            entry = {"template_id": tid, "count_a": ca, "count_b": cb}
            if ca == 0 and cb > 0:
                new_in_b.append(entry)
            elif ca > 0 and cb == 0:
                disappeared.append(entry)
            elif cb > ca:
                increased.append(entry)
            elif cb < ca:
                decreased.append(entry)

        return {
            "new_in_b": new_in_b,
            "disappeared": disappeared,
            "increased": increased,
            "decreased": decreased,
        }

    # ------------------------------------------------------------------
    # 6. find_first_occurrence
    # ------------------------------------------------------------------

    def find_first_occurrence(self, template_id: str) -> dict[str, Any]:
        """Earliest event matching a template."""
        rows = self.store.query(
            "SELECT * FROM events WHERE template_id = ? ORDER BY timestamp ASC LIMIT 1",
            [template_id],
        )
        total_rows = self.store.query(
            "SELECT COUNT(*) AS cnt FROM events WHERE template_id = ?",
            [template_id],
        )
        total = total_rows[0]["cnt"] if total_rows else 0
        return {
            "template_id": template_id,
            "first_event": rows[0] if rows else None,
            "total_occurrences": total,
        }

    # ------------------------------------------------------------------
    # 7. correlate
    # ------------------------------------------------------------------

    def correlate(
        self,
        template_a: str,
        template_b: str,
        max_lag_seconds: float = 60.0,
    ) -> dict[str, Any]:
        """Check whether template_a events tend to precede template_b events
        within *max_lag_seconds*."""
        a_events = self.store.query(
            "SELECT event_id, timestamp FROM events WHERE template_id = ? ORDER BY timestamp",
            [template_a],
        )
        b_events = self.store.query(
            "SELECT event_id, timestamp FROM events WHERE template_id = ? ORDER BY timestamp",
            [template_b],
        )

        pairs: list[dict[str, Any]] = []
        b_idx = 0
        for a in a_events:
            # Advance b_idx to first b event at or after a's timestamp
            while b_idx < len(b_events) and b_events[b_idx]["timestamp"] < a["timestamp"]:
                b_idx += 1
            # Scan forward in b looking for matches within the lag window
            for j in range(b_idx, len(b_events)):
                diff = (b_events[j]["timestamp"] - a["timestamp"]).total_seconds()
                if diff > max_lag_seconds:
                    break
                if diff >= 0:
                    pairs.append(
                        {
                            "event_a": a["event_id"],
                            "event_b": b_events[j]["event_id"],
                            "lag_seconds": diff,
                        }
                    )
                    break  # one match per a event

        correlation_found = len(pairs) > 0
        avg_lag = sum(p["lag_seconds"] for p in pairs) / len(pairs) if pairs else 0.0

        return {
            "template_a": template_a,
            "template_b": template_b,
            "correlation_found": correlation_found,
            "avg_lag_seconds": avg_lag,
            "sample_pairs": pairs[:20],  # bounded
        }

    # ------------------------------------------------------------------
    # 8. get_service_dependencies
    # ------------------------------------------------------------------

    def get_service_dependencies(self) -> dict[str, Any]:
        """Analyze trace_id/request_id to find which services call which."""
        # For each request_id (or trace_id), order events by timestamp.
        # The service of event N calls the service of event N+1 if they differ.
        rows = self.store.query(
            "SELECT request_id, trace_id, service, timestamp "
            "FROM events "
            "WHERE request_id IS NOT NULL OR trace_id IS NOT NULL "
            "ORDER BY COALESCE(request_id, trace_id), timestamp"
        )

        dep_counts: dict[tuple[str, str], int] = {}
        prev_group: str | None = None
        prev_service: str | None = None

        for r in rows:
            group = r["request_id"] or r["trace_id"]
            svc = r["service"]
            if group == prev_group and svc != prev_service and prev_service is not None:
                key = (prev_service, svc)
                dep_counts[key] = dep_counts.get(key, 0) + 1
            prev_group = group
            prev_service = svc

        deps = sorted(
            [{"from": k[0], "to": k[1], "request_count": v} for k, v in dep_counts.items()],
            key=lambda d: d["request_count"],
            reverse=True,
        )

        return {"dependencies": deps}


# ======================================================================
# TOOL_DEFINITIONS – JSON-Schema-style descriptions for LLM registration
# ======================================================================

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_logs",
        "description": "Full-text search on log messages with optional time, service, and level filters. Returns bounded results with total count.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring to search for in log messages."},
                "time_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Optional [start, end] ISO-8601 timestamps.",
                },
                "service": {"type": "string", "description": "Filter to a specific service name."},
                "level": {
                    "type": "string",
                    "enum": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"],
                    "description": "Filter to a specific log level.",
                },
                "limit": {"type": "integer", "default": 50, "description": "Maximum number of results to return."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_template_stats",
        "description": "Get time-bucketed occurrence counts and spike detection for a log template.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "The template cluster ID."},
                "time_range": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Optional [start, end] ISO-8601 timestamps.",
                },
            },
            "required": ["template_id"],
        },
    },
    {
        "name": "get_context",
        "description": "Get events surrounding a target event by timestamp within the same service.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The target event ID."},
                "before": {"type": "integer", "default": 5, "description": "Number of preceding events to return."},
                "after": {"type": "integer", "default": 5, "description": "Number of following events to return."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "trace_request",
        "description": "Reconstruct the full path of a request across services using its request_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "description": "The request ID to trace."},
            },
            "required": ["request_id"],
        },
    },
    {
        "name": "compare_windows",
        "description": "Compare template occurrence counts between two time windows to find new, disappeared, increased, or decreased patterns.",
        "parameters": {
            "type": "object",
            "properties": {
                "window_a": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[start, end] ISO-8601 timestamps for the first window.",
                },
                "window_b": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[start, end] ISO-8601 timestamps for the second window.",
                },
            },
            "required": ["window_a", "window_b"],
        },
    },
    {
        "name": "find_first_occurrence",
        "description": "Find the earliest event matching a template and count total occurrences.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {"type": "string", "description": "The template cluster ID."},
            },
            "required": ["template_id"],
        },
    },
    {
        "name": "correlate",
        "description": "Check whether events of template_a tend to precede events of template_b within a time lag.",
        "parameters": {
            "type": "object",
            "properties": {
                "template_a": {"type": "string", "description": "First template ID (expected to occur first)."},
                "template_b": {"type": "string", "description": "Second template ID (expected to follow)."},
                "max_lag_seconds": {
                    "type": "number",
                    "default": 60.0,
                    "description": "Maximum lag in seconds between paired events.",
                },
            },
            "required": ["template_a", "template_b"],
        },
    },
    {
        "name": "get_service_dependencies",
        "description": "Analyze trace/request IDs to discover which services call which others.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

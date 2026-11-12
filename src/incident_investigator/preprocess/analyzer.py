"""Time bucketing and anomaly scoring for log events."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta

from incident_investigator.models import BucketCount, LogEvent, TemplateCluster


class LogAnalyzer:
    """Groups events into time buckets and scores templates for anomalies."""

    @staticmethod
    def bucket_events(events: list[LogEvent], bucket_minutes: int = 1) -> list[BucketCount]:
        """Group *events* by ``template_id`` + time bucket and count occurrences."""
        buckets: dict[tuple[str, datetime], dict] = defaultdict(
            lambda: {"count": 0, "level": None, "service": "unknown"}
        )

        for ev in events:
            tid = ev.template_id or "unknown"
            # Floor to bucket boundary
            ts = ev.timestamp
            bucket_start = ts.replace(second=0, microsecond=0) - timedelta(minutes=ts.minute % bucket_minutes)
            key = (tid, bucket_start)
            buckets[key]["count"] += 1
            buckets[key]["level"] = ev.level
            buckets[key]["service"] = ev.service

        return [
            BucketCount(
                template_id=tid,
                bucket_start=bs,
                bucket_minutes=bucket_minutes,
                count=info["count"],
                level=info["level"],
                service=info["service"],
            )
            for (tid, bs), info in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1]))
        ]

    @staticmethod
    def score_anomalies(
        templates: list[TemplateCluster],
        buckets: list[BucketCount],
        z_threshold: float = 3.0,
    ) -> list[TemplateCluster]:
        """Score each template for anomalous behaviour and return sorted list (desc)."""
        # Group bucket counts by template_id
        bucket_map: dict[str, list[int]] = defaultdict(list)
        for b in buckets:
            bucket_map[b.template_id].append(b.count)

        # Determine overall time range for "new template" heuristic
        all_starts = [b.bucket_start for b in buckets]
        if all_starts:
            global_min = min(all_starts)
            global_max = max(all_starts)
            time_range = (global_max - global_min).total_seconds()
            recency_threshold = global_max - timedelta(seconds=time_range * 0.10) if time_range > 0 else global_max
        else:
            recency_threshold = datetime.max

        scored: list[TemplateCluster] = []
        for tpl in templates:
            counts = bucket_map.get(tpl.template_id, [])
            tpl_copy = tpl.model_copy()

            if len(counts) >= 2:
                mean = sum(counts) / len(counts)
                variance = sum((c - mean) ** 2 for c in counts) / len(counts)
                std = math.sqrt(variance) if variance > 0 else 0.0

                if std > 0:
                    max_z = max((c - mean) / std for c in counts)
                    tpl_copy.anomaly_score = max(tpl_copy.anomaly_score, max_z)
                    if max_z >= z_threshold:
                        tpl_copy.is_anomaly = True

            # Recency heuristic: first_seen in the last 10% of time range
            if tpl_copy.first_seen is not None and tpl_copy.first_seen >= recency_threshold:
                tpl_copy.is_anomaly = True
                tpl_copy.anomaly_score = max(tpl_copy.anomaly_score, z_threshold)

            scored.append(tpl_copy)

        scored.sort(key=lambda t: t.anomaly_score, reverse=True)
        return scored

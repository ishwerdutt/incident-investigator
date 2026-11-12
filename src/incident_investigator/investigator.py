"""High-level public interface for incident_investigator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

from incident_investigator.ingest.parsers import AutoParser
from incident_investigator.llm.provider import LLMProvider, OpenAIProvider
from incident_investigator.models import (
    InvestigationConfig,
    InvestigationEvent,
    InvestigationResult,
    LogEvent,
)
from incident_investigator.orchestrator import InvestigationOrchestrator
from incident_investigator.preprocess.analyzer import LogAnalyzer
from incident_investigator.preprocess.drain import TemplateExtractor
from incident_investigator.preprocess.redactor import Redactor
from incident_investigator.store.duckdb_store import LogStore


class Investigator:
    """High-level facade for running log incident investigations.

    Example:
        investigator = Investigator()
        result = investigator.investigate(
            files=["app.log"],
            hint="Database checkout timeouts",
        )
        print(result.report_markdown())
    """

    def __init__(
        self,
        llm: LLMProvider | None = None,
        config: InvestigationConfig | None = None,
        on_event: Callable[[InvestigationEvent], None] | None = None,
    ) -> None:
        self.config = config or InvestigationConfig()
        self.llm = llm or OpenAIProvider(default_model=self.config.openai_model)
        self.on_event = on_event
        self.redactor = Redactor()
        self.parser = AutoParser()
        self.extractor = TemplateExtractor()
        self.analyzer = LogAnalyzer()

    async def investigate_async(
        self,
        files: Sequence[str | Path] | None = None,
        raw_logs: Sequence[str] | None = None,
        hint: str | None = None,
    ) -> InvestigationResult:
        """Run an investigation asynchronously."""
        events: list[LogEvent] = []

        # 1. Parse files
        if files:
            for file_path in files:
                p = Path(file_path)
                if not p.exists():
                    raise FileNotFoundError(f"Log file not found: {p}")
                file_content = await asyncio.to_thread(p.read_text, encoding="utf-8", errors="replace")
                file_lines = file_content.splitlines(keepends=True)
                file_parser = AutoParser(file_lines)
                for line_num, line in enumerate(file_lines, start=1):
                    cleaned = line.strip()
                    if not cleaned:
                        continue
                    evt = file_parser.parse_line(cleaned, str(p), line_num)
                    if evt:
                        events.append(evt)

        # 2. Parse raw log lines if provided
        if raw_logs:
            raw_parser = AutoParser(list(raw_logs))
            for idx, line in enumerate(raw_logs, start=1):
                cleaned = line.strip()
                if not cleaned:
                    continue
                evt = raw_parser.parse_line(cleaned, "memory", idx)
                if evt:
                    events.append(evt)

        if not events:
            raise ValueError("No parseable log events found in inputs.")
        self.last_events = events

        # 3. Redact sensitive info
        for evt in events:
            evt.message = self.redactor.redact(evt.message)

        # 4. Extract templates via Drain3
        for evt in events:
            tpl_id = self.extractor.add_log_message(evt.message)
            evt.template_id = tpl_id

        templates = self.extractor.get_templates()

        # 5. Bucket events and score anomalies
        buckets = self.analyzer.bucket_events(events, bucket_minutes=self.config.bucket_minutes)
        templates = self.analyzer.score_anomalies(
            templates,
            buckets,
            z_threshold=self.config.anomaly_z_threshold,
        )

        # 6. Initialize DuckDB log store
        store = LogStore(db_path=":memory:")
        try:
            store.ingest_events(events)
            store.ingest_templates(templates)
            store.ingest_buckets(buckets)

            # 7. Run Orchestrator
            orchestrator = InvestigationOrchestrator(
                llm=self.llm,
                config=self.config,
                on_event=self.on_event,
            )
            result = await orchestrator.investigate(
                events=events,
                templates=templates,
                buckets=buckets,
                store=store,
                user_hint=hint,
            )
            return result
        finally:
            store.close()

    def investigate(
        self,
        files: Sequence[str | Path] | None = None,
        raw_logs: Sequence[str] | None = None,
        hint: str | None = None,
    ) -> InvestigationResult:
        """Synchronous wrapper for investigate_async."""
        return asyncio.run(self.investigate_async(files=files, raw_logs=raw_logs, hint=hint))

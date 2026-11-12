"""Core data models for the incident investigator engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

import ulid
from pydantic import BaseModel, Field


def _new_id(prefix: str = "evt") -> str:
    return f"{prefix}_{ulid.new().str.lower()}"


# ---------------------------------------------------------------------------
# Log primitives
# ---------------------------------------------------------------------------


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
    UNKNOWN = "UNKNOWN"


class LogEvent(BaseModel):
    """A single normalised log line."""

    event_id: str = Field(default_factory=lambda: _new_id("evt"))
    timestamp: datetime
    level: LogLevel = LogLevel.UNKNOWN
    service: str = "unknown"
    message: str
    template_id: str | None = None
    trace_id: str | None = None
    request_id: str | None = None
    source_file: str = ""
    line_number: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_line: str = ""


# ---------------------------------------------------------------------------
# Template clustering
# ---------------------------------------------------------------------------


class TemplateCluster(BaseModel):
    """A Drain3 template cluster with metadata."""

    template_id: str = Field(default_factory=lambda: _new_id("tpl"))
    pattern: str  # e.g. "Connection to <*> timed out after <*>ms"
    sample_message: str = ""
    total_count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    services: list[str] = Field(default_factory=list)
    is_anomaly: bool = False
    anomaly_score: float = 0.0


class BucketCount(BaseModel):
    """Template occurrence count within a time bucket."""

    template_id: str
    bucket_start: datetime
    bucket_minutes: int = 1
    count: int = 0
    level: LogLevel = LogLevel.UNKNOWN
    service: str = "unknown"


# ---------------------------------------------------------------------------
# Evidence ledger
# ---------------------------------------------------------------------------


class HypothesisStatus(str, Enum):
    OPEN = "open"
    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class EvidenceItem(BaseModel):
    """A single piece of evidence linking a hypothesis to log events."""

    evidence_id: str = Field(default_factory=lambda: _new_id("evi"))
    hypothesis_id: str
    event_ids: list[str] = Field(
        default_factory=list,
        description="Referenced event IDs in the log store",
    )
    summary: str
    supports: bool  # True = supports hypothesis, False = refutes
    tool_name: str = ""
    tool_call_id: str = ""
    earliest_timestamp: datetime | None = None
    latest_timestamp: datetime | None = None
    explanation: str = ""


class Hypothesis(BaseModel):
    """A candidate root cause with evidence trail."""

    id: str = Field(default_factory=lambda: _new_id("hyp"))
    statement: str
    predicted_evidence: list[str] = Field(default_factory=list)
    falsification_conditions: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.OPEN
    confidence: float = 0.0  # 0.0 – 1.0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    critic_notes: str | None = None


# ---------------------------------------------------------------------------
# Investigation inputs & outputs
# ---------------------------------------------------------------------------


class IncidentBrief(BaseModel):
    """Output of the Triage agent: summarises the incident."""

    incident_window_start: datetime
    incident_window_end: datetime
    affected_services: list[str] = Field(default_factory=list)
    primary_symptoms: list[str] = Field(default_factory=list)
    anomalous_templates: list[TemplateCluster] = Field(default_factory=list)
    user_hint: str | None = None


class InvestigationConfig(BaseModel):
    """Runtime config for a single investigation."""

    max_rounds: int = 3
    max_tool_calls_per_agent: int = 8
    max_total_tokens: int = 200_000
    confidence_threshold: float = 0.7
    bucket_minutes: int = 1
    anomaly_z_threshold: float = 3.0
    openai_model: str = "gpt-4o"
    openai_model_cheap: str = "gpt-4o-mini"


class InvestigationEvent(BaseModel):
    """A live event emitted during investigation (for SSE / callbacks)."""

    event_type: str  # STAGE_CHANGED, TOOL_CALLED, TOOL_RESULT, LEDGER_UPDATED, REPORT_READY
    stage: str | None = None
    agent: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvestigationResult(BaseModel):
    """Final output of an investigation."""

    incident_id: str = Field(default_factory=lambda: _new_id("inc"))
    executive_summary: str = ""
    root_cause: str = ""
    confidence: float = 0.0
    incident_timeline: list[dict[str, Any]] = Field(default_factory=list)
    supported_hypothesis: Hypothesis | None = None
    ruled_out_hypotheses: list[Hypothesis] = Field(default_factory=list)
    verified_evidence_event_ids: list[str] = Field(default_factory=list)
    recommended_mitigations: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    total_tokens_used: int = 0
    total_tool_calls: int = 0
    investigation_duration_seconds: float = 0.0
    brief: IncidentBrief | None = None

    def report_markdown(self, brief: IncidentBrief | None = None) -> str:
        """Render the result as a rich Markdown report."""
        from incident_investigator.report.renderers import MarkdownRenderer

        return MarkdownRenderer().render(self, brief=brief or self.brief)

    def report_json(self, indent: int = 2) -> str:
        """Render the result as a structured JSON string."""
        from incident_investigator.report.renderers import JsonRenderer

        return JsonRenderer().render(self, indent=indent)

    def report_html(self, brief: IncidentBrief | None = None) -> str:
        """Render the result as a self-contained HTML post-mortem report."""
        from incident_investigator.report.renderers import HtmlRenderer

        return HtmlRenderer().render(self, brief=brief or self.brief)

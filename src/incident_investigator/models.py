"""Core data models for the incident investigator engine."""

from __future__ import annotations

from datetime import datetime
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
    timestamp: datetime = Field(default_factory=datetime.utcnow)


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

    def report_markdown(self) -> str:
        """Render the result as a Markdown report."""
        lines: list[str] = []
        lines.append(f"# Incident Report: {self.incident_id}\n")
        lines.append(f"## Executive Summary\n{self.executive_summary}\n")
        lines.append(f"## Root Cause\n{self.root_cause}\n")
        lines.append(f"**Confidence:** {self.confidence:.0%}\n")

        if self.incident_timeline:
            lines.append("## Timeline")
            for entry in self.incident_timeline:
                ts = entry.get("timestamp", "?")
                desc = entry.get("description", "")
                lines.append(f"- **{ts}**: {desc}")
            lines.append("")

        if self.supported_hypothesis:
            h = self.supported_hypothesis
            lines.append(f"## Supported Hypothesis\n**{h.statement}**\n")
            for ev in h.evidence:
                tag = "✅" if ev.supports else "❌"
                lines.append(f"- {tag} {ev.summary} (events: {', '.join(ev.event_ids[:5])})")
            lines.append("")

        if self.ruled_out_hypotheses:
            lines.append("## Ruled Out Hypotheses")
            for h in self.ruled_out_hypotheses:
                lines.append(f"- ~~{h.statement}~~ — {h.critic_notes or 'refuted'}")
            lines.append("")

        if self.recommended_mitigations:
            lines.append("## Recommended Mitigations")
            for m in self.recommended_mitigations:
                lines.append(f"- {m}")
            lines.append("")

        if self.unknowns:
            lines.append("## Unknowns & Limitations")
            for u in self.unknowns:
                lines.append(f"- {u}")
            lines.append("")

        lines.append(f"---\n*Tokens used: {self.total_tokens_used:,} | "
                      f"Tool calls: {self.total_tool_calls} | "
                      f"Duration: {self.investigation_duration_seconds:.1f}s*")
        return "\n".join(lines)

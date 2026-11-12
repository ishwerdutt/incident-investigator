"""Reporter agent: produces the final investigation report."""

from __future__ import annotations

import json

from incident_investigator.agents.base import BaseAgent
from incident_investigator.ledger.evidence_ledger import EvidenceLedger
from incident_investigator.models import (
    HypothesisStatus,
    IncidentBrief,
    InvestigationResult,
)


class ReporterAgent(BaseAgent):
    """Constructs an :class:`InvestigationResult` strictly from ledger evidence."""

    async def write_report(
        self,
        ledger: EvidenceLedger,
        brief: IncidentBrief,
    ) -> InvestigationResult:
        system_prompt = (
            "You are a technical report writer for incident investigations. "
            "Write a report based ONLY on the evidence provided. "
            "Every claim must reference specific event IDs. "
            "Respond with a JSON object:\n"
            "{\n"
            '  "executive_summary": "...",\n'
            '  "root_cause": "...",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "incident_timeline": [{"timestamp": "...", "description": "..."}],\n'
            '  "recommended_mitigations": ["..."],\n'
            '  "unknowns": ["..."]\n'
            "}\n"
            "Respond ONLY with JSON, no markdown fences."
        )

        user_content = (
            f"## Incident Brief\n"
            f"Window: {brief.incident_window_start} – {brief.incident_window_end}\n"
            f"Services: {', '.join(brief.affected_services)}\n"
            f"Symptoms: {', '.join(brief.primary_symptoms)}\n\n"
            f"## Evidence Ledger\n{ledger.to_summary()}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = await self.llm.complete(messages, model=self.model)
        self._track_usage(resp.usage)

        raw = resp.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.removesuffix("```")
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}

        # Build result from ledger + LLM output
        supported = ledger.get_leading_hypothesis()
        ruled_out = [h for h in ledger.get_all_hypotheses() if h.status == HypothesisStatus.REFUTED]
        all_event_ids: list[str] = []
        for h in ledger.get_all_hypotheses():
            for e in h.evidence:
                all_event_ids.extend(e.event_ids)

        return InvestigationResult(
            executive_summary=data.get("executive_summary", ""),
            root_cause=data.get("root_cause", ""),
            confidence=data.get("confidence", supported.confidence if supported else 0.0),
            incident_timeline=data.get("incident_timeline", []),
            supported_hypothesis=supported,
            ruled_out_hypotheses=ruled_out,
            verified_evidence_event_ids=list(set(all_event_ids)),
            recommended_mitigations=data.get("recommended_mitigations", []),
            unknowns=data.get("unknowns", []),
        )

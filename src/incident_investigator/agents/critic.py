"""Critic agent: challenges the leading hypothesis."""

from __future__ import annotations

import json
from datetime import datetime

from incident_investigator.agents.base import BaseAgent
from incident_investigator.ledger.evidence_ledger import EvidenceLedger


class CriticAgent(BaseAgent):
    """Reviews the leading hypothesis, checking temporal ordering,
    correlation-vs-causation, and alternative explanations."""

    async def evaluate(
        self,
        ledger: EvidenceLedger,
        symptom_time: datetime,
    ) -> dict:
        leading = ledger.get_leading_hypothesis()
        if leading is None:
            return {
                "verdict": "insufficient",
                "notes": "No leading hypothesis to evaluate.",
                "hypothesis_id": "",
            }

        # Temporal check
        temporal_ok = ledger.validate_temporal_order(leading.id, symptom_time)

        system_prompt = (
            "You are a critical-thinking SRE reviewer. "
            "Evaluate the leading root-cause hypothesis. Challenge it on:\n"
            "1. Correlation vs causation\n"
            "2. Temporal ordering (does the cause precede the symptom?)\n"
            "3. Alternative explanations\n"
            "Respond with a JSON object:\n"
            '{"verdict": "approved" | "challenged" | "insufficient", "notes": "..."}\n'
            "Respond ONLY with JSON, no markdown fences."
        )

        evidence_summary = "\n".join(
            f"- {'✅' if e.supports else '❌'} {e.summary} (events: {len(e.event_ids)})" for e in leading.evidence
        )

        user_content = (
            f"Hypothesis: {leading.statement}\n"
            f"Status: {leading.status.value}\n"
            f"Confidence: {leading.confidence:.2f}\n"
            f"Temporal check: {'PASS' if temporal_ok else 'FAIL – cause appears after symptom'}\n"
            f"Evidence:\n{evidence_summary}\n"
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
            data = {"verdict": "insufficient", "notes": raw}

        result = {
            "verdict": data.get("verdict", "insufficient"),
            "notes": data.get("notes", ""),
            "hypothesis_id": leading.id,
        }

        # Record critic notes on the hypothesis
        leading.critic_notes = result["notes"]

        return result

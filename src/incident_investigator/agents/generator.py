"""Hypothesis generator agent: proposes falsifiable hypotheses."""

from __future__ import annotations

import json

from incident_investigator.agents.base import BaseAgent
from incident_investigator.ledger.evidence_ledger import EvidenceLedger
from incident_investigator.models import (
    Hypothesis,
    HypothesisStatus,
    IncidentBrief,
)


class HypothesisGeneratorAgent(BaseAgent):
    """Generates 3-5 falsifiable hypotheses from an :class:`IncidentBrief`."""

    async def generate(
        self,
        brief: IncidentBrief,
        ledger: EvidenceLedger,
    ) -> list[Hypothesis]:
        system_prompt = (
            "You are a senior SRE forming root-cause hypotheses. "
            "Given an incident brief, produce a JSON array of 3 to 5 hypotheses. "
            "Each hypothesis object must have:\n"
            '- "statement" (str): a concise falsifiable claim\n'
            '- "predicted_evidence" (list[str]): what we should find if true\n'
            '- "falsification_conditions" (list[str]): what would disprove it\n'
            "Respond ONLY with a JSON array, no markdown fences."
        )
        user_content = (
            f"Incident window: {brief.incident_window_start} – {brief.incident_window_end}\n"
            f"Affected services: {', '.join(brief.affected_services)}\n"
            f"Symptoms: {', '.join(brief.primary_symptoms)}\n"
        )
        if brief.user_hint:
            user_content += f"Operator hint: {brief.user_hint}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = await self.llm.complete(messages, model=self.model)
        self._track_usage(resp.usage)

        raw = resp.content.strip()
        # Strip potential markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.removesuffix("```")
            raw = raw.strip()

        items = json.loads(raw)
        hypotheses: list[Hypothesis] = []
        for item in items:
            hyp = Hypothesis(
                statement=item["statement"],
                predicted_evidence=item.get("predicted_evidence", []),
                falsification_conditions=item.get("falsification_conditions", []),
                status=HypothesisStatus.OPEN,
            )
            ledger.add_hypothesis(hyp)
            hypotheses.append(hyp)

        return hypotheses

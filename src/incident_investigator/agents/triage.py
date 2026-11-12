"""Triage agent: produces an IncidentBrief from raw summaries."""

from __future__ import annotations

import json

from incident_investigator.agents.base import BaseAgent
from incident_investigator.models import IncidentBrief


class TriageAgent(BaseAgent):
    """Analyses template and anomaly summaries to produce a structured
    :class:`IncidentBrief`."""

    async def analyze(
        self,
        template_summary: str,
        anomaly_summary: str,
        user_hint: str | None = None,
    ) -> IncidentBrief:
        system_prompt = (
            "You are an expert incident triage engineer. "
            "Given log template and anomaly summaries, produce a JSON object "
            "with the following fields:\n"
            "- incident_window_start (ISO-8601 datetime)\n"
            "- incident_window_end (ISO-8601 datetime)\n"
            "- affected_services (list of strings)\n"
            "- primary_symptoms (list of strings)\n"
            "- anomalous_templates (empty list)\n"
            "- user_hint (string or null)\n"
            "Respond ONLY with valid JSON, no markdown fences."
        )
        user_content = f"## Templates\n{template_summary}\n\n## Anomalies\n{anomaly_summary}"
        if user_hint:
            user_content += f"\n\n## Operator hint\n{user_hint}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = await self.llm.complete(messages, model=self.model)
        self._track_usage(resp.usage)

        # Parse JSON from response
        raw = resp.content.strip()
        # Strip potential markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.removesuffix("```")
            raw = raw.strip()

        data = json.loads(raw)
        return IncidentBrief(**data)

"""Hypothesis tester agent: gathers evidence using tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from incident_investigator.agents.base import BaseAgent
from incident_investigator.ledger.evidence_ledger import EvidenceLedger
from incident_investigator.llm.provider import LLMProvider
from incident_investigator.models import (
    EvidenceItem,
    Hypothesis,
    HypothesisStatus,
)


class HypothesisTesterAgent(BaseAgent):
    """Tests a single hypothesis by calling investigation tools in a loop."""

    def __init__(
        self,
        name: str,
        llm: LLMProvider,
        tools_definitions: list[dict],
        tool_executor: Callable[..., Any],
        model: str | None = None,
    ) -> None:
        super().__init__(name, llm, model)
        self.tools_definitions = tools_definitions
        self.tool_executor = tool_executor

    async def test(
        self,
        hypothesis: Hypothesis,
        ledger: EvidenceLedger,
        max_tool_calls: int = 5,
    ) -> Hypothesis:
        """Run a tool-calling loop to gather evidence for *hypothesis*."""
        ledger.update_status(hypothesis.id, HypothesisStatus.TESTING)

        system_prompt = (
            "You are an SRE investigator testing a hypothesis about a production incident. "
            "You have access to tools that query a log store. "
            "Call tools to gather evidence. After gathering evidence, respond with a JSON object:\n"
            '{"supports": true/false, "summary": "...", "event_ids": [...], "confidence": 0.0-1.0}\n'
            "Respond ONLY with the JSON object when you have enough evidence."
        )

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Hypothesis: {hypothesis.statement}\n"
                    f"Predicted evidence: {json.dumps(hypothesis.predicted_evidence)}\n"
                    f"Falsification conditions: {json.dumps(hypothesis.falsification_conditions)}\n"
                    "Use the available tools to test this hypothesis."
                ),
            },
        ]

        calls_made = 0
        while calls_made < max_tool_calls:
            resp = await self.llm.complete(
                messages,
                tools=self.tools_definitions if self.tools_definitions else None,
                model=self.model,
            )
            self._track_usage(resp.usage)

            # If no tool calls, the LLM has reached a conclusion
            if not resp.tool_calls:
                # Parse the final verdict
                self._process_verdict(resp.content, hypothesis, ledger)
                break

            # Execute each tool call
            for tc in resp.tool_calls:
                calls_made += 1
                self.tool_call_count += 1
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}

                result = self.tool_executor(tool_name, **args)

                # Feed tool result back
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc.get("id", f"call_{calls_made}"),
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": func.get("arguments", "{}"),
                                },
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{calls_made}"),
                        "content": json.dumps(result) if isinstance(result, dict) else str(result),
                    }
                )

                hypothesis.tests_run.append(tool_name)

                if calls_made >= max_tool_calls:
                    break
        else:
            # Budget exhausted – ask for a final verdict without tools
            messages.append(
                {
                    "role": "user",
                    "content": "Tool call budget exhausted. Provide your final verdict now as JSON.",
                }
            )
            resp = await self.llm.complete(messages, model=self.model)
            self._track_usage(resp.usage)
            self._process_verdict(resp.content, hypothesis, ledger)

        return hypothesis

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_verdict(self, content: str, hypothesis: Hypothesis, ledger: EvidenceLedger) -> None:
        """Parse the LLM's final JSON verdict and update the ledger."""
        raw = content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.removesuffix("```")
            raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # If we can't parse, record as inconclusive
            data = {"supports": False, "summary": raw, "event_ids": [], "confidence": 0.0}

        evidence = EvidenceItem(
            hypothesis_id=hypothesis.id,
            event_ids=data.get("event_ids", []),
            summary=data.get("summary", ""),
            supports=data.get("supports", False),
            tool_name="hypothesis_tester",
        )
        ledger.add_evidence(hypothesis.id, evidence)

        confidence = data.get("confidence", 0.0)
        if isinstance(confidence, (int, float)):
            hypothesis.confidence = float(confidence)

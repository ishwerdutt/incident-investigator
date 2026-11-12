"""Base class shared by all investigation agents."""

from __future__ import annotations

from incident_investigator.llm.provider import LLMProvider


class BaseAgent:
    """Abstract base for every investigation agent."""

    def __init__(
        self,
        name: str,
        llm: LLMProvider,
        model: str | None = None,
    ) -> None:
        self.name = name
        self.llm = llm
        self.model = model
        self.token_usage: dict[str, int] = {"prompt": 0, "completion": 0}
        self.tool_call_count: int = 0

    def _track_usage(self, usage: dict) -> None:
        """Accumulate token counts from an LLM response."""
        self.token_usage["prompt"] += usage.get("prompt_tokens", 0)
        self.token_usage["completion"] += usage.get("completion_tokens", 0)

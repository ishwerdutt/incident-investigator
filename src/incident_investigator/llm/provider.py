"""LLM provider abstraction and implementations."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import openai


@dataclass
class LLMResponse:
    """Normalised response from any LLM provider."""

    content: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol every LLM backend must satisfy."""

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
    ) -> LLMResponse: ...


class OpenAIProvider:
    """Production provider backed by the OpenAI API."""

    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o") -> None:
        self.default_model = default_model
        self.client = openai.AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": model or self.default_model,
            "messages": messages,
        }
        if tools:
            formatted_tools = []
            for t in tools:
                if isinstance(t, dict) and t.get("type") == "function" and "function" in t:
                    formatted_tools.append(t)
                elif isinstance(t, dict):
                    formatted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t.get("name"),
                                "description": t.get("description", ""),
                                "parameters": t.get("parameters", {}),
                            },
                        }
                    )
            kwargs["tools"] = formatted_tools

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        # Parse tool calls from OpenAI format
        parsed_tool_calls: list[dict] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                parsed_tool_calls.append(
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        usage_info = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
        }

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=parsed_tool_calls,
            usage=usage_info,
        )


class MockLLMProvider:
    """Deterministic provider that returns pre-configured responses in order.

    Useful for testing without hitting a real API.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        if self._index >= len(self._responses):
            content = ""
        else:
            content = self._responses[self._index]
            self._index += 1

        return LLMResponse(
            content=content,
            tool_calls=[],
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )

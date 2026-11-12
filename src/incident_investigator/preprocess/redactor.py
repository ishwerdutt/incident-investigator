"""PII and secret redactor for log messages."""

from __future__ import annotations

import re


class Redactor:
    """Replaces PII and secrets in text with redaction placeholders."""

    _patterns: list[tuple[re.Pattern[str], str]]

    def __init__(self) -> None:
        self._patterns = [
            # Bearer / JWT tokens  (must come before generic key patterns)
            (
                re.compile(r"Bearer\s+eyJ[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*", re.IGNORECASE),
                "<REDACTED_TOKEN>",
            ),
            # Email addresses
            (
                re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
                "<REDACTED_EMAIL>",
            ),
            # IPv6 addresses  (simplified – matches common representations)
            (
                re.compile(
                    r"(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}"  # full
                    r"|(?:[0-9a-fA-F]{1,4}:){1,7}:"  # trailing ::
                    r"|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}"  # :: in middle
                    r"|(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}"
                    r"|(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}"
                    r"|(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}"
                    r"|(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}"
                    r"|[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}"
                    r"|::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}"
                    r"|::"
                ),
                "<REDACTED_IPV6>",
            ),
            # IPv4 addresses
            (
                re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
                "<REDACTED_IP>",
            ),
            # AWS AKIA keys
            (
                re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
                "<REDACTED_KEY>",
            ),
            # sk- style API keys  (OpenAI, Stripe, etc.)
            (
                re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
                "<REDACTED_KEY>",
            ),
            # Hex strings 32+ chars after key= or token=
            (
                re.compile(r"((?:key|token)=)[0-9a-fA-F]{32,}"),
                r"\1<REDACTED_KEY>",
            ),
        ]

    def redact(self, text: str) -> str:
        """Return *text* with PII / secrets replaced by placeholders."""
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        return text

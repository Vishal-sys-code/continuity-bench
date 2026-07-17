#!/usr/bin/env python3
"""
systems/providers.py — Unified provider abstraction for OpenAI & Anthropic
===========================================================================

Wraps the OpenAI and Anthropic Python SDKs behind a common interface so
that the baseline and treatment proxies can swap providers transparently.

Both providers accept OpenAI-compatible messages[] format (list of
{role, content} dicts). The Anthropic adapter translates this into the
Anthropic API shape (system prompt extraction, role mapping).

Environment variables:
    OPENAI_API_KEY    — required for the OpenAI provider
    ANTHROPIC_API_KEY — required for the Anthropic provider

Default models:
    OpenAI    → gpt-4o-mini
    Anthropic → claude-3-5-sonnet-20240620
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import openai
import anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Provider response ──────────────────────────────────────────────────────────

@dataclass
class ProviderResponse:
    """Normalised response from any provider."""
    text: str
    model: str
    provider: str
    latency_ms: float = 0.0
    time_to_first_token_ms: Optional[float] = None
    raw: Any = None  # raw SDK response for debugging


# ─── Abstract base ──────────────────────────────────────────────────────────────

class Provider(ABC):
    """Abstract provider interface."""

    name: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        """Send a chat completion request and return the response."""
        ...


# ─── OpenAI provider ────────────────────────────────────────────────────────────

class OpenAIProvider(Provider):
    """OpenAI chat completions via the official SDK."""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.default_model = default_model
        self._client = openai.OpenAI(
            api_key=self.api_key,
            max_retries=5,
            timeout=300.0,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        model = model or self.default_model
        t0 = time.perf_counter()

        response = self._client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )

        latency_ms = (time.perf_counter() - t0) * 1000
        text = response.choices[0].message.content or ""

        return ProviderResponse(
            text=text,
            model=response.model,
            provider=self.name,
            latency_ms=latency_ms,
            raw=response,
        )


# ─── Anthropic provider ─────────────────────────────────────────────────────────

class AnthropicProvider(Provider):
    """Anthropic messages API via the official SDK.

    Translates OpenAI-format messages[] into Anthropic's format:
    - Extracts any system messages into the top-level `system` param.
    - Maps roles: "user" → "user", "assistant" → "assistant".
    - Ignores unsupported roles gracefully.
    """

    name = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "claude-sonnet-5",
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.default_model = default_model
        self._client = anthropic.Anthropic(
            api_key=self.api_key,
            max_retries=5,
            timeout=300.0,
        )

    def _translate_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, list[dict[str, str]]]:
        """Split OpenAI messages into (system_prompt, anthropic_messages).

        Anthropic requires system messages to be passed as a separate
        parameter, not inside the messages array.  Additionally, the
        messages array must start with a user turn.
        """
        system_parts: list[str] = []
        api_messages: list[dict[str, str]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content)
            elif role in ("user", "assistant"):
                api_messages.append({"role": role, "content": content})
            # Skip unknown roles (e.g., "tool", "function") gracefully

        system_prompt = "\n\n".join(system_parts) if system_parts else ""

        # Anthropic requires messages to start with a user turn.
        # If the first message is an assistant turn, prepend a placeholder.
        if api_messages and api_messages[0]["role"] == "assistant":
            api_messages.insert(
                0,
                {"role": "user", "content": "(continuing conversation)"},
            )

        # Anthropic requires alternating user/assistant turns.
        # Merge consecutive same-role messages.
        merged: list[dict[str, str]] = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(dict(msg))

        return system_prompt, merged

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        model = model or self.default_model
        system_prompt, api_messages = self._translate_messages(messages)

        t0 = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)

        latency_ms = (time.perf_counter() - t0) * 1000

        # Extract text from content blocks
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        text = "".join(text_parts)

        return ProviderResponse(
            text=text,
            model=response.model,
            provider=self.name,
            latency_ms=latency_ms,
            raw=response,
        )


# ─── Gemini provider ────────────────────────────────────────────────────────────

class GeminiProvider(Provider):
    """Google Gemini API via the google-genai SDK.

    Translates OpenAI-format messages[] into Gemini's format:
    - Extracts system messages into the system_instruction param.
    - Maps roles: "user" → "user", "assistant" → "model".
    """

    name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-2.0-flash",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.default_model = default_model
        from google import genai
        self._client = genai.Client(api_key=self.api_key)

    def _translate_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Split OpenAI messages into (system_instruction, gemini_contents)."""
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})

        system_instruction = "\n\n".join(system_parts) if system_parts else None

        # Gemini requires alternating user/model turns and must start with user.
        if contents and contents[0]["role"] == "model":
            contents.insert(0, {"role": "user", "parts": [{"text": "(continuing conversation)"}]})

        # Merge consecutive same-role turns
        merged: list[dict[str, Any]] = []
        for c in contents:
            if merged and merged[-1]["role"] == c["role"]:
                merged[-1]["parts"].extend(c["parts"])
            else:
                merged.append(c)

        return system_instruction, merged

    def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        model = model or self.default_model
        system_instruction, contents = self._translate_messages(messages)

        t0 = time.perf_counter()

        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_instruction:
            config.system_instruction = system_instruction

        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        latency_ms = (time.perf_counter() - t0) * 1000
        text = response.text or ""

        return ProviderResponse(
            text=text,
            model=model,
            provider=self.name,
            latency_ms=latency_ms,
            raw=response,
        )


# ─── Provider registry ──────────────────────────────────────────────────────────

PROVIDERS: dict[str, type[Provider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def create_provider(name: str, **kwargs: Any) -> Provider:
    """Instantiate a provider by name.

    Parameters
    ----------
    name : str
        Provider name ("openai" or "anthropic").
    **kwargs
        Forwarded to the provider constructor (api_key, default_model, etc.).

    Raises
    ------
    ValueError
        If the provider name is not registered.
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {list(PROVIDERS.keys())}"
        )
    return cls(**kwargs)


def get_provider_names() -> list[str]:
    """Return the list of registered provider names."""
    return list(PROVIDERS.keys())

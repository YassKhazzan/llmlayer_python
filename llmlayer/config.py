"""
Central place for loading env vars & user overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


_PROVIDER_ENV_MAP = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


@dataclass(slots=True, frozen=True)
class Credentials:
    api_key: str            # LLMLAYER_API_KEY  (Bearer)
    provider: str           # e.g. "openai"
    provider_key: str       # provider-specific key

    @staticmethod
    def from_env(
        *,
        provider: str | None = None,
        api_key: str | None = None,
        provider_key: str | None = None,
    ) -> "Credentials":
        # --- resolve LLMLayer key ---
        api_key = api_key or os.getenv("LLMLAYER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing LLMLAYER_API_KEY environment variable or explicit api_key"
            )

        # --- resolve provider ---
        provider = (provider or os.getenv("LLMLAYER_PROVIDER") or "openai").lower()
        if provider not in _PROVIDER_ENV_MAP:
            raise RuntimeError(
                f"Unsupported provider '{provider}'. "
                f"Supported: {', '.join(_PROVIDER_ENV_MAP)}"
            )

        # --- resolve provider key ---
        provider_key = (
            provider_key
            or os.getenv(_PROVIDER_ENV_MAP[provider])
            or os.getenv("LLMLAYER_PROVIDER_KEY")  # generic fallback
        )
        if not provider_key:
            raise RuntimeError(
                f"Missing provider key. Set {_PROVIDER_ENV_MAP[provider]} or pass provider_key."
            )

        return Credentials(api_key=api_key, provider=provider, provider_key=provider_key)

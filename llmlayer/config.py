"""
Central place for loading env vars & user overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True, frozen=True)
class Credentials:
    api_key: str            # LLMLAYER_API_KEY  (Bearer)
    provider_key: Optional[str] = None       # provider-specific key

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        provider_key: Optional[str] = None
    ) -> "Credentials":
        # --- resolve LLMLayer key ---
        api_key = api_key or os.getenv("LLMLAYER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing LLMLAYER_API_KEY environment variable or explicit api_key"
            )


        # --- resolve provider key ---
        provider_key = (
            provider_key
            or os.getenv("LLMLAYER_PROVIDER_KEY")  # generic fallback
            or None
        )

        return Credentials(api_key=api_key, provider_key=provider_key)

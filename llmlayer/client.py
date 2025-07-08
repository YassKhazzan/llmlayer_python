from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Dict, Generator, Optional

import httpx

from ._version import __version__  # noqa: F401
from .exceptions import (
    AuthenticationError,
    InvalidRequest,
    InternalServerError,
    LLMLayerError,
    ProviderError,
    RateLimitError,
)
from .models import SearchRequest, SimplifiedSearchResponse

_ERROR_MAP = {
    "validation_error": InvalidRequest,
    "authentication_error": AuthenticationError,
    "provider_error": ProviderError,
    "rate_limit": RateLimitError,
    "internal_error": InternalServerError,
}


class LLMLayerClient:
    """
    Minimal constructor::

        client = LLMLayerClient(
            api_key="LLM_API_KEY",
            provider="openai",
            provider_key="OPENAI_API_KEY"
        )

    Each parameter can fall back to an env variable:

    | param         | env var                |
    |---------------|------------------------|
    | api_key       | LLMLAYER_API_KEY       |
    | provider      | LLMLAYER_PROVIDER      |
    | provider_key  | <PROVIDER>_API_KEY     |

    Example: `OPENAI_API_KEY`, `GEMINI_API_KEY`, …
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        provider: str | None = None,
        provider_key: str | None = None,
        base_url: str = "https://api.llmlayer.dev",
        timeout: float | httpx.Timeout = 60.0,
        client: httpx.Client | None = None,
    ):
        # ---- resolve credentials (explicit > env) -------------------- #
        self.api_key = api_key or os.getenv("LLMLAYER_API_KEY")
        if not self.api_key:
            raise AuthenticationError("LLMLAYER_API_KEY missing (or api_key not provided)")

        self.provider = (provider or os.getenv("LLMLAYER_PROVIDER") or "openai").lower()
        self.provider_key = (
            provider_key
            or os.getenv(f"{self.provider.upper()}_API_KEY")
            or os.getenv("LLMLAYER_PROVIDER_KEY")
        )
        if not self.provider_key:
            raise AuthenticationError(
                f"{self.provider.upper()}_API_KEY missing (or provider_key not provided)"
            )

        # ---- http client plumbing ----------------------------------- #
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._external_client = client
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": f"llmlayer-sdk/{__version__}"},
        )

    # ----------------- public ---------------------------------------- #
    def search(self, **kwargs) -> SimplifiedSearchResponse:
        body = self._build_body(kwargs)
        r = self._client.post(f"{self.base_url}/api/v1/search", json=body)
        return self._handle_response(r)

    def search_stream(self, **kwargs) -> Generator[dict[str, Any], None, None]:
        body = self._build_body(kwargs)
        with self._client.stream("POST", f"{self.base_url}/api/v1/search_stream", json=body) as r:
            if r.status_code != 200:
                self._raise_http(r)
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = json.loads(line[5:].strip())
                if "error_type" in payload or "error" in payload:
                    raise self._map_err(payload)
                yield payload

    # ----------------- async variants -------------------------------- #
    async def asearch(self, **kwargs) -> SimplifiedSearchResponse:
        body = self._build_body(kwargs)
        async with self._maybe_client() as ac:
            r = await ac.post(f"{self.base_url}/api/v1/search", json=body)
            return self._handle_response(r)

    async def asearch_stream(self, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
        body = self._build_body(kwargs)
        async with self._maybe_client() as ac:
            async with ac.stream("POST", f"{self.base_url}/api/v1/search_stream", json=body) as r:
                if r.status_code != 200:
                    await self._raise_http_async(r)
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = json.loads(line[5:].strip())
                    if "error_type" in payload or "error" in payload:
                        raise self._map_err(payload)
                    yield payload

    # ----------------- internals ------------------------------------- #
    def _build_body(self, user_kwargs: dict) -> dict:
        req = SearchRequest(
            provider=self.provider,
            provider_key=self.provider_key,
            **user_kwargs,
        )
        return json.loads(req.json(exclude_none=True))

    def _handle_response(self, r: httpx.Response) -> SimplifiedSearchResponse:
        if r.status_code != 200:
            self._raise_http(r)
        payload = r.json()
        if "error_type" in payload:
            raise self._map_err(payload)
        return SimplifiedSearchResponse.model_validate(payload)

    # error helpers
    def _raise_http(self, r: httpx.Response):
        try:
            payload = r.json()
        except Exception:
            r.raise_for_status()
        raise self._map_err(payload, status_code=r.status_code)

    async def _raise_http_async(self, r: httpx.Response):
        try:
            payload = await r.json()
        except Exception:
            r.raise_for_status()
        raise self._map_err(payload, status_code=r.status_code)

    @staticmethod
    def _map_err(payload: dict, status_code: int | None = None) -> LLMLayerError:
        etype = payload.get("error_type") or payload.get("type")
        exc = _ERROR_MAP.get(etype, LLMLayerError)
        msg = payload.get("message") or payload.get("error") or str(payload)
        return exc(msg)

    # async client CM
    def _maybe_client(self):
        if self._external_client:
            return _PassThrough(self._external_client)
        return httpx.AsyncClient(
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": f"llmlayer-sdk/{__version__}"},
        )

    # context mgr plumbing
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._external_client:
            self._client.close()


class _PassThrough:
    def __init__(self, c: httpx.AsyncClient):
        self._c = c

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, exc_type, exc, tb):
        return False  # don't suppress

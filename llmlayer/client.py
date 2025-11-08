from __future__ import annotations

"""
LLMLayer Python client — aligned to backend api_v2.py

Implements:
- POST /api/v2/answer
- POST /api/v2/answer_stream            (SSE; frames carry {"type": ...}, content frames use {"type":"answer"})
- POST /api/v2/youtube_transcript
- POST /api/v2/get_pdf_content
- POST /api/v2/scrape                   (v2: multi-format request/response)
- POST /api/v2/web_search
- POST /api/v2/map                      (v2: response uses statusCode)
- POST /api/v2/crawl_stream             (SSE; frames: page/usage/done/error; request takes a single seed url + formats)

Notes:
- Streaming explicitly rejects answer_type="json" (server-side and client-side).
- /answer_stream frames are data-only SSE lines; we parse "data:" buffers into JSON.
"""

import json
import os
import warnings
from typing import Any, AsyncGenerator, Dict, Generator, Iterable, Optional, Type, TypeVar

import httpx

from ._version import __version__
from .exceptions import (
    AuthenticationError,
    InvalidRequest,
    InternalServerError,
    LLMLayerError,
    ProviderError,
    RateLimitError,
)
from .models import (
    # Core Answer
    SearchRequest,
    AnswerResponse,
    # Utilities
    YTRequest,
    YTResponse,
    PDFRequest,
    PDFResponse,
    ScrapeRequest,
    ScraperResponse,
    WebSearchRequest,
    WebSearchResponse,
    # Map
    MapRequest,
    MapResponse,
    # Crawl
    CrawlRequest,
)

# -------------------------------
# Error mapping helpers
# -------------------------------

_ERROR_MAP_BY_TYPE: Dict[str, Type[LLMLayerError]] = {
    # shared
    "validation_error": InvalidRequest,
    "authentication_error": AuthenticationError,
    "provider_error": ProviderError,
    "rate_limit": RateLimitError,
    "internal_error": InternalServerError,
    # backend-specific
    "scraping_error": InternalServerError,
    "search_error": InternalServerError,
    "map_error": InternalServerError,
    "crawl_stream_error": InternalServerError,
}


def _class_for_status(status_code: int) -> type[LLMLayerError]:
    if status_code == 400:
        return InvalidRequest
    if status_code in (401, 403):
        return AuthenticationError
    if status_code in (408, 504):
        return InternalServerError
    if status_code == 429:
        return RateLimitError
    if status_code >= 500:
        return InternalServerError
    return LLMLayerError


T = TypeVar("T")


class LLMLayerClient:
    """Typed client for LLMLayer v2 API and utility endpoints."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.llmlayer.dev",
        timeout: float | httpx.Timeout = 80.0,
        client: Optional[httpx.Client] = None,
        async_client: Optional[httpx.AsyncClient] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        # ---- Credentials ----
        self.api_key = api_key or os.getenv("LLMLAYER_API_KEY")
        if not self.api_key:
            raise AuthenticationError("LLMLAYER_API_KEY missing (or api_key not provided)")

        # ---- HTTP plumbing ----
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

        # Default headers
        self._default_headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": f"llmlayer/{__version__}",
        }
        if extra_headers:
            self._default_headers.update({k: v for k, v in extra_headers.items() if v is not None})

        # Sync client
        if client is not None and not isinstance(client, httpx.Client):
            raise TypeError("`client` must be an instance of httpx.Client")
        if client is None:
            self._client = httpx.Client(timeout=timeout, headers=self._default_headers)
            self._owns_client = True
        else:
            client.headers.update(self._default_headers)
            self._client = client
            self._owns_client = False

        # Async client
        if async_client is not None and not isinstance(async_client, httpx.AsyncClient):
            raise TypeError("`async_client` must be an instance of httpx.AsyncClient")
        if async_client is None:
            self._async_client = None  # lazily created per use
            self._owns_async_client = True
        else:
            async_client.headers.update(self._default_headers)
            self._async_client = async_client
            self._owns_async_client = False

    # ======================================================================
    # Answer — Sync
    # ======================================================================

    def answer(
        self,
        /,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
        **params: Any,
    ) -> AnswerResponse:
        """Blocking answer call (POST /api/v2/answer)."""
        body = self._build_body(params)
        r = self._client.post(
            f"{self.base_url}/api/v2/answer",
            json=body,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._handle_response(r)

    def stream_answer(
        self,
        /,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
        **params: Any,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming answer via Server-Sent Events (POST /api/v2/answer_stream).

        Frames are JSON objects with a `type` field, e.g.:
          {"type":"sources","data":[...]}
          {"type":"images","data":[...]}
          {"type":"answer","content":"<delta text>"}          # <— content frames use 'answer'
          {"type":"usage","input_tokens":...,"output_tokens":...,"model_cost":...,"llmlayer_cost":...}
          {"type":"done","response_time":"<sec.xx>"}

        Note: streaming does NOT support `answer_type="json"`.
        """
        at = str(params.get("answer_type", "")).lower()
        if at == "json":
            raise InvalidRequest("Streaming does not support structured JSON output (answer_type='json')")

        body = self._build_body(params)
        with self._client.stream(
            "POST",
            f"{self.base_url}/api/v2/answer_stream",
            json=body,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        ) as r:
            if r.status_code != 200:
                self._raise_http_streaming(r)

            data_buf: list[str] = []
            for line in r.iter_lines():
                if line is None:
                    continue
                if line == "":
                    if not data_buf:
                        continue
                    raw = "".join(data_buf).strip()  # single-line per frame is typical; join w/o newlines for safety
                    data_buf.clear()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    self._maybe_raise_error_payload(payload)
                    yield payload
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_buf.append(line[5:])
                    continue
                # ignore other SSE fields

    # ======================================================================
    # Answer — Async
    # ======================================================================

    async def answer_async(
        self,
        /,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
        **params: Any,
    ) -> AnswerResponse:
        body = self._build_body(params)
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/answer",
                json=body,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._handle_response(r)

    async def stream_answer_async(
        self,
        /,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
        **params: Any,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        at = str(params.get("answer_type", "")).lower()
        if at == "json":
            raise InvalidRequest("Streaming does not support structured JSON output (answer_type='json')")

        body = self._build_body(params)
        async with self._get_async_client() as ac:
            async with ac.stream(
                "POST",
                f"{self.base_url}/api/v2/answer_stream",
                json=body,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            ) as r:
                if r.status_code != 200:
                    await self._raise_http_streaming_async(r)

                data_buf: list[str] = []
                async for line in r.aiter_lines():
                    if line is None:
                        continue
                    if line == "":
                        if not data_buf:
                            continue
                        raw = "".join(data_buf).strip()
                        data_buf.clear()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self._maybe_raise_error_payload(payload)
                        yield payload
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_buf.append(line[5:])
                        continue

    # ======================================================================
    # Utilities — Sync (v2)
    # ======================================================================

    def get_youtube_transcript(
        self,
        url: str,
        *,
        language: Optional[str] = None,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> YTResponse:
        payload = YTRequest(url=url, language=language).model_dump(exclude_none=True)
        r = self._client.post(
            f"{self.base_url}/api/v2/youtube_transcript",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._parse_model(r, YTResponse)

    def get_pdf_content(
        self,
        url: str,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> PDFResponse:
        payload = PDFRequest(url=url).model_dump()
        r = self._client.post(
            f"{self.base_url}/api/v2/get_pdf_content",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._parse_model(r, PDFResponse)

    def scrape(
        self,
        url: str,
        *,
        formats: Iterable[str] = ("markdown",),   # 'markdown' | 'html' | 'screenshot' | 'pdf'
        include_images: bool = True,
        include_links: bool = True,
        advanced_proxy: bool = False,
        main_content_only: bool = False,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ScraperResponse:
        payload = ScrapeRequest(
            url=url,
            formats=list(formats),
            include_images=include_images,
            include_links=include_links,
            advanced_proxy = advanced_proxy,
            main_content_only = main_content_only,
        ).model_dump()
        r = self._client.post(
            f"{self.base_url}/api/v2/scrape",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._parse_model(r, ScraperResponse)

    def search_web(
        self,
        query: str,
        *,
        search_type: str = "general",       # 'general' | 'news' | 'shopping' | 'videos' | 'images' | 'scholar'
        location: str = "us",
        recency: Optional[str] = None,      # 'hour' | 'day' | 'week' | 'month' | 'year'
        domain_filter: Optional[list[str]] = None,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> WebSearchResponse:
        payload = WebSearchRequest(
            query=query,
            search_type=search_type,
            location=location,
            recency=recency,
            domain_filter=domain_filter,
        ).model_dump(exclude_none=True)
        r = self._client.post(
            f"{self.base_url}/api/v2/web_search",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._parse_model(r, WebSearchResponse)

    def map(
        self,
        url: str,
        *,
        ignore_sitemap: bool = False,
        include_subdomains: bool = False,
        search: Optional[str] = None,
        limit: int = 5000,
        timeout_ms: Optional[int] = 45000,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> MapResponse:
        payload = MapRequest(
            url=url,
            ignoreSitemap=ignore_sitemap,
            includeSubdomains=include_subdomains,
            search=search,
            limit=limit,
            timeout=timeout_ms,
        ).model_dump(mode="json", exclude_none=True)
        r = self._client.post(
            f"{self.base_url}/api/v2/map",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        )
        return self._parse_model(r, MapResponse)

    def crawl_stream(
        self,
        url: str,
        *,
        max_pages: int = 25,
        max_depth: int = 2,
        timeout_seconds: Optional[float] = 60.0,
        include_subdomains: bool = False,
        include_links: bool = True,
        include_images: bool = True,
        advanced_proxy: bool = False,
        main_content_only: bool = False,
        formats: Iterable[str] = ("markdown",),
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming crawl proxy (POST /api/v2/crawl_stream) — frames with 'page'/'usage'/'done'/'error'.
        Request takes a single seed URL and a list of desired artifacts ('markdown','html','screenshot','pdf').
        """
        payload = CrawlRequest(
            url=url,
            max_pages=max_pages,
            max_depth=max_depth,
            timeout=timeout_seconds,
            include_subdomains=include_subdomains,
            include_links=include_links,
            include_images=include_images,
            advanced_proxy=advanced_proxy,
            main_content_only=main_content_only,
            formats=list(formats),
        ).model_dump(mode="json", exclude_none=True)

        with self._client.stream(
            "POST",
            f"{self.base_url}/api/v2/crawl_stream",
            json=payload,
            timeout=(timeout if timeout is not None else self._timeout),
            headers=(headers or None),
        ) as r:
            if r.status_code != 200:
                self._raise_http_streaming(r)

            data_buf: list[str] = []
            for line in r.iter_lines():
                if line is None:
                    continue
                if line == "":
                    if not data_buf:
                        continue
                    raw = "".join(data_buf).strip()
                    data_buf.clear()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    self._maybe_raise_error_payload(payload)
                    yield payload
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_buf.append(line[5:])
                    continue

    # ======================================================================
    # Utilities — Async (v2)
    # ======================================================================

    async def get_youtube_transcript_async(
        self,
        url: str,
        *,
        language: Optional[str] = None,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> YTResponse:
        payload = YTRequest(url=url, language=language).model_dump(exclude_none=True)
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/youtube_transcript",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._parse_model(r, YTResponse)

    async def get_pdf_content_async(
        self,
        url: str,
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> PDFResponse:
        payload = PDFRequest(url=url).model_dump()
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/get_pdf_content",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._parse_model(r, PDFResponse)

    async def scrape_async(
        self,
        url: str,
        *,
        formats: Iterable[str] = ("markdown",),
        include_images: bool = True,
        include_links: bool = True,
        advanced_proxy: bool = False,
        main_content_only: bool = False,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ScraperResponse:
        payload = ScrapeRequest(
            url=url,
            formats=list(formats),
            include_images=include_images,
            include_links=include_links,
            advanced_proxy=advanced_proxy,
            main_content_only = main_content_only,
        ).model_dump()
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/scrape",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._parse_model(r, ScraperResponse)

    async def search_web_async(
        self,
        query: str,
        *,
        search_type: str = "general",
        location: str = "us",
        recency: Optional[str] = None,
        domain_filter: Optional[list[str]] = None,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> WebSearchResponse:
        payload = WebSearchRequest(
            query=query,
            search_type=search_type,
            location=location,
            recency=recency,
            domain_filter=domain_filter,
        ).model_dump(exclude_none=True)
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/web_search",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._parse_model(r, WebSearchResponse)

    async def map_async(
        self,
        url: str,
        *,
        ignore_sitemap: bool = False,
        include_subdomains: bool = False,
        search: Optional[str] = None,
        limit: int = 5000,
        timeout_ms: Optional[int] = 45000,
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> MapResponse:
        payload = MapRequest(
            url=url,
            ignoreSitemap=ignore_sitemap,
            includeSubdomains=include_subdomains,
            search=search,
            limit=limit,
            timeout=timeout_ms,
        ).model_dump(mode="json", exclude_none=True)
        async with self._get_async_client() as ac:
            r = await ac.post(
                f"{self.base_url}/api/v2/map",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            )
            return self._parse_model(r, MapResponse)

    async def crawl_stream_async(
        self,
        url: str,
        *,
        max_pages: int = 25,
        max_depth: int = 2,
        timeout_seconds: Optional[float] = 60.0,
        include_subdomains: bool = False,
        include_links: bool = True,
        include_images: bool = True,
        advanced_proxy: bool = False,
        main_content_only: bool = False,
        formats: Iterable[str] = ("markdown",),
        timeout: float | httpx.Timeout | None = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        payload = CrawlRequest(
            url=url,
            max_pages=max_pages,
            max_depth=max_depth,
            timeout=timeout_seconds,
            include_subdomains=include_subdomains,
            include_links=include_links,
            include_images=include_images,
            advanced_proxy=advanced_proxy,
            main_content_only=main_content_only,
            formats=list(formats),
        ).model_dump(mode="json", exclude_none=True)

        async with self._get_async_client() as ac:
            async with ac.stream(
                "POST",
                f"{self.base_url}/api/v2/crawl_stream",
                json=payload,
                timeout=(timeout if timeout is not None else self._timeout),
                headers=(headers or None),
            ) as r:
                if r.status_code != 200:
                    await self._raise_http_streaming_async(r)

                data_buf: list[str] = []
                async for line in r.aiter_lines():
                    if line is None:
                        continue
                    if line == "":
                        if not data_buf:
                            continue
                        raw = "".join(data_buf).strip()
                        data_buf.clear()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self._maybe_raise_error_payload(payload)
                        yield payload
                        continue
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_buf.append(line[5:])
                        continue

    # ======================================================================
    # Backwards-compatible aliases (DeprecationWarning)
    # ======================================================================

    def search_stream(self, *args, **kwargs):  # type: ignore[override]
        warnings.warn("search_stream() is deprecated; use stream_answer()", DeprecationWarning, stacklevel=2)
        return self.stream_answer(*args, **kwargs)

    def search(self, *args, **kwargs):  # type: ignore[override]
        warnings.warn("search() is deprecated; use answer()", DeprecationWarning, stacklevel=2)
        return self.answer(*args, **kwargs)

    async def asearch(self, *args, **kwargs):  # type: ignore[override]
        warnings.warn("asearch() is deprecated; use answer_async()", DeprecationWarning, stacklevel=2)
        return await self.answer_async(*args, **kwargs)

    async def asearch_stream(self, *args, **kwargs):  # type: ignore[override]
        warnings.warn("asearch_stream() is deprecated; use stream_answer_async()", DeprecationWarning, stacklevel=2)
        async for evt in self.stream_answer_async(*args, **kwargs):
            yield evt

    # ======================================================================
    # Lifecycle / context managers
    # ======================================================================

    def close(self) -> None:
        if getattr(self, "_owns_client", False) and hasattr(self, "_client"):
            try:
                self._client.close()
            finally:
                pass

    async def aclose(self) -> None:
        if getattr(self, "_owns_async_client", False) and getattr(self, "_async_client", None) is not None:
            try:
                await self._async_client.aclose()
            finally:
                pass

    def __enter__(self) -> "LLMLayerClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    async def __aenter__(self) -> "LLMLayerClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # ======================================================================
    # Internals
    # ======================================================================

    def _build_body(self, user_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize strings to lower where backend expects that
        if "answer_type" in user_kwargs and isinstance(user_kwargs["answer_type"], str):
            user_kwargs["answer_type"] = user_kwargs["answer_type"].lower()
        if "search_type" in user_kwargs and isinstance(user_kwargs["search_type"], str):
            user_kwargs["search_type"] = user_kwargs["search_type"].lower()

        # Allow dict for json_schema — serialize to JSON string for backend
        js = user_kwargs.get("json_schema")
        if isinstance(js, dict):
            user_kwargs = {**user_kwargs, "json_schema": json.dumps(js)}

        # Build and dump via pydantic model for validation/trimming
        req = SearchRequest(**user_kwargs)
        return req.model_dump(exclude_none=True)

    def _parse_model(self, r: httpx.Response, model: Type[T]) -> T:
        if r.status_code != 200:
            self._raise_http(r)
        try:
            payload = r.json()
        except Exception:
            raise LLMLayerError("Malformed success response (expected JSON)")
        if isinstance(payload, dict) and ("error_type" in payload or "error" in payload or "detail" in payload):
            raise self._map_err(payload, status_code=r.status_code, request_id=r.headers.get("x-request-id"))
        try:
            return model.model_validate(payload)  # type: ignore[attr-defined]
        except Exception as e:
            raise LLMLayerError(f"Failed to validate response payload: {e}")

    def _handle_response(self, r: httpx.Response) -> AnswerResponse:
        return self._parse_model(r, AnswerResponse)

    def _raise_http(self, r: httpx.Response) -> None:
        request_id = r.headers.get("x-request-id")
        text = None
        payload: Dict[str, Any] | None = None
        try:
            payload = r.json()
        except Exception:
            try:
                text = r.text
            except Exception:
                text = None
        raise self._map_err(payload or {"error": text or f"HTTP {r.status_code}"}, status_code=r.status_code, request_id=request_id)

    def _raise_http_streaming(self, r: httpx.Response) -> None:
        request_id = r.headers.get("x-request-id")
        body = None
        try:
            body = r.read()
        except Exception:
            pass
        payload: Dict[str, Any] | None = None
        if body:
            try:
                payload = json.loads(body.decode(r.encoding or "utf-8"))
            except Exception:
                payload = None
        raise self._map_err(payload or {"error": f"HTTP {r.status_code}"}, status_code=r.status_code, request_id=request_id)

    async def _raise_http_streaming_async(self, r: httpx.Response) -> None:
        request_id = r.headers.get("x-request-id")
        body = None
        try:
            body = await r.aread()
        except Exception:
            pass
        payload: Dict[str, Any] | None = None
        if body:
            try:
                payload = json.loads(body.decode(r.encoding or "utf-8"))
            except Exception:
                payload = None
        raise self._map_err(payload or {"error": f"HTTP {r.status_code}"}, status_code=r.status_code, request_id=request_id)

    def _maybe_raise_error_payload(self, payload: Dict[str, Any]) -> None:
        # FastAPI 'detail' envelope
        if "detail" in payload and isinstance(payload["detail"], dict):
            raise self._map_err(payload)

        # Explicit error frame
        if payload.get("type") == "error":
            raise self._map_err(payload)

        # Simple early error string codes used early in stream
        err = payload.get("error")
        if err:
            lower = str(err).lower()
            if lower in {"missing_model", "missing_query", "invalid_model"} or "structured output" in lower:
                raise InvalidRequest(err)
            raise LLMLayerError(err)

        if "error_type" in payload:
            raise self._map_err(payload)

    def _map_err(
        self,
        payload: Dict[str, Any] | None,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> LLMLayerError:
        data = payload or {}
        if isinstance(data, dict) and "detail" in data and isinstance(data["detail"], dict):
            data = data["detail"]  # unwrap FastAPI envelope
        etype = data.get("error_type") or data.get("type")  # support both keys
        cls = _ERROR_MAP_BY_TYPE.get(str(etype)) if etype else None
        if cls is None and status_code is not None:
            cls = _class_for_status(status_code)
        if cls is None:
            cls = LLMLayerError
        message = data.get("message") or data.get("error") or (json.dumps(payload) if payload else f"HTTP {status_code}")
        if request_id:
            message = f"{message} (request_id={request_id})"
        return cls(message)

    def _get_async_client(self):
        if self._async_client is not None:
            return _AsyncPassThrough(self._async_client)
        return _AsyncOwnedClient(self._default_headers, self._timeout)


class _AsyncPassThrough:
    def __init__(self, client: httpx.AsyncClient):
        self._c = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._c

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _AsyncOwnedClient:
    def __init__(self, headers: Dict[str, str], timeout: float | httpx.Timeout):
        self._headers = headers
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        self._client = httpx.AsyncClient(timeout=self._timeout, headers=self._headers)
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._client is not None:
                await self._client.aclose()
        finally:
            self._client = None

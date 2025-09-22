# LLMLayer Python SDK (v0.2.0)

> **Search → Reason → Cite** with one call.
>
> Official Python client for the **LLMLayer Search & Answer API**.

---

## Table of Contents

* [Overview](#overview)
* [Features](#features)
* [Requirements](#requirements)
* [Installation](#installation)
* [Answer API](#answer-api)
  * [Blocking answer](#blocking-answer)
  * [Streaming (SSE)](#streaming-sse)
* [Configuration](#configuration)
* [API Reference](#api-reference)
  * [Client](#class-llmlayerclient)
  * [Core Methods](#core-methods)
  * [Answer Parameters](#answer-parameters)
  * [Streaming Events](#streaming-events)
  * [Errors](#errors)
  * [Models (Types)](#models-types)
* [Utilities](#utilities)
  * [YouTube Transcript](#youtube-transcript)
  * [PDF Content](#pdf-content)
  * [Scrape](#scrape)
  * [Web Search](#web-search)
* [Advanced Tips](#advanced-tips)
* [Version & Changelog](#version--changelog)
* [License](#license)
* [Support](#support)

---

## Overview

**LLMLayer** combines web search, context building, and LLM reasoning in a single API. This SDK provides a clean interface with **sync/async parity**, robust **SSE streaming**, and **utility endpoints** for transcripts, scraping, PDF extraction, and vertical web search.

---

## Features

* **Clean API** – `answer()` and `stream_answer()` match the backend contract.
* **Async parity** – `answer_async()` and `stream_answer_async()` with the same params.
* **Rich utilities** – YouTube transcripts, PDF extraction, universal scrape (markdown/html/pdf/screenshot), and web search (general/news/images/videos/shopping/scholar).
* **Typed errors** – Clear exceptions for auth, validation, rate limits, provider failures.
* **Lightweight** – Only `httpx` + `pydantic` at runtime.
* **HTTP/1.1 only** – No HTTP/2 dependency.

---

## Requirements

* **Python ≥ 3.9**

---

## Installation

```bash
pip install llmlayer
```

---

## Answer API

### Blocking answer

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient(
    api_key="<LLMLAYER_API_KEY>",
)

resp = client.answer(
    query="Why is the sky blue?",
    model="openai/gpt-4.1-mini",
    return_sources=True,
)

print(resp.llm_response)
print("sources:", len(resp.sources))
print("latency (s):", resp.response_time)
```

### Streaming (SSE)

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient(api_key="<LLMLAYER_API_KEY>")

for event in client.stream_answer(
    query="Explain brown dwarfs in two short paragraphs",
    model="openai/gpt-4.1-mini",
    return_sources=True,
):
    t = event.get("type")
    if t == "llm":
        print(event["content"], end="", flush=True)
    elif t == "sources":
        print("\n[SOURCES]", len(event.get("data", [])))
    elif t == "images":
        print("\n[IMAGES]", len(event.get("data", [])))
    elif t == "usage":
        print("\n[USAGE]", event)
    elif t == "done":
        print("\n✓ finished in", event.get("response_time"), "s")
```

> **Note:** Streaming **does not** support `answer_type="json"` (structured output). Use blocking `answer()` with `json_schema` for JSON responses.

---

## Configuration

You can pass options to the constructor or via environment variables (constructor wins):

| Variable | Purpose |
|----------|---------|
| `LLMLAYER_API_KEY` | **Required.** Sent as `Authorization: Bearer <key>` |

**Constructor options**

* `base_url` (default `https://api.llmlayer.dev`) — point to local/dev if needed.
* `timeout` — default 60s.
* `client` / `async_client` — reuse your own `httpx` clients (headers injected).
* `extra_headers` — merged on top of Authorization & User-Agent.


---

## API Reference

### `class LLMLayerClient`

**Constructor**

```python
LLMLayerClient(
    api_key: str | None = None,
    base_url: str = "https://api.llmlayer.dev",
    timeout: float | httpx.Timeout = 60.0,
    client: httpx.Client | None = None,
    async_client: httpx.AsyncClient | None = None,
    extra_headers: dict[str, str] | None = None,
)
```

### Core Methods

```python
answer(**params) -> SimplifiedSearchResponse
stream_answer(**params) -> typing.Generator[dict, None, None]
answer_async(**params) -> SimplifiedSearchResponse
stream_answer_async(**params) -> typing.AsyncGenerator[dict, None]
```

### Answer Parameters


| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `str` | — | **Required.** The user's question/instruction. |
| `model` | `str` | — | **Required.** Provider model id, e.g. `openai/gpt-4.1-mini`. |
| `location` | `str` | `"us"` | Geo bias used by search. |
| `system_prompt` | `str \| None` | `None` | Custom system prompt for non-JSON answers. |
| `response_language` | `str` | `"auto"` | Autodetect output language or force a specific language code. |
| `answer_type` | `"markdown" \| "html" \| "json"` | `"markdown"` | Output format. **If `"json"`, you must also pass `json_schema`. Not supported by streaming.** |
| `search_type` | `"general" \| "news"` | `"general"` | Search vertical/bias for the context builder. (For other verticals, use `search_web`.) |
| `json_schema` | `str \| dict \| None` | `None` | **Required when `answer_type="json"`.** You may pass a `dict`; the client will JSON-serialize it. |
| `citations` | `bool` | `False` | If `True`, embed citation markers (e.g., `[1]`) in the answer body. |
| `return_sources` | `bool` | `False` | Include aggregated `sources` in the final response (and emit a `sources` event during streaming). |
| `return_images` | `bool` | `False` | Include `images` in the final response (and emit an `images` event during streaming). |
| `date_filter` | `"hour" \| "day" \| "week" \| "month" \| "year" \| "anytime"` | `"anytime"` | Recency bias for search. |
| `max_tokens` | `int` | `1500` | Maximum output tokens from the LLM. |
| `temperature` | `float` | `0.7` | Sampling temperature (creativity). |
| `domain_filter` | `list[str] \| None` | `None` | Domain constraints (include `['nature.com']`, exclude with `['-wikipedia.org']`). |
| `max_queries` | `int` | `1` | How many search sub-queries the router should generate. |
| `search_context_size` | `"low" \| "medium" \| "high"` | `"medium"` | Controls how much context is aggregated before hitting the LLM. |

### Streaming Events

Your server emits JSON frames over SSE (`content-type: text/event-stream`). Possible events:

| `type` | Payload keys | Meaning |
|--------|--------------|---------|
| `llm` | `content: str` | Partial LLM text |
| `sources` | `data: list[dict]` | Aggregated sources |
| `images` | `data: list[dict]` | Image results |
| `usage` | `input_tokens: int`, `output_tokens: int`, `model_cost: float \| None`, `llmlayer_cost: float` | Token/cost summary |
| `done` | `response_time: str` | Completion signal |
| `error` | `error: str` | Error frame (raises) |

The SDK's streaming helpers handle multi-line `data:` chunks, `[DONE]` sentinels, and early error frames.

### Errors

All exceptions inherit from `llmlayer.exceptions.LLMLayerError`:

* `InvalidRequest` — 400 (missing/invalid params; early SSE errors like `missing_model`)
* `AuthenticationError` — 401/403 (missing/invalid LLMLayer key)
* `RateLimitError` — 429
* `ProviderError` — upstream LLM provider errors (mapped by the backend)
* `InternalServerError` — 5xx from LLMLayer

**Example**

```python
from llmlayer import LLMLayerClient
from llmlayer.exceptions import AuthenticationError, InvalidRequest

client = LLMLayerClient(api_key="...")

try:
    resp = client.answer(query="explain kv cache", model="openai/gpt-4.1-mini")
except AuthenticationError as e:
    print("Auth failed:", e)
except InvalidRequest as e:
    print("Bad params:", e)
```

### Models (Types)

```python
class SimplifiedSearchResponse(BaseModel):
    llm_response: str | dict
    response_time: float | str  # e.g., "1.23"
    input_tokens: int
    output_tokens: int
    sources: list[dict] = []
    images: list[dict] = []
    model_cost: float | None = None
    llmlayer_cost: float | None = None

class YTResponse(BaseModel):
    transcript: str
    url: str
    cost: float | None
    language: str | None

class PDFResponse(BaseModel):
    text: str
    pages: int
    url: str
    status_code: int
    cost: float | None

class ScraperResponse(BaseModel):
    markdown: str
    html: str | None
    pdf_data: str | None          # base64
    screenshot_data: str | None   # base64
    url: str
    status_code: int
    cost: float | None

class WebSearchResponse(BaseModel):
    results: list[dict]
    cost: float | None
```

---

## Utilities

### YouTube Transcript

**Endpoint:** `POST /api/v1/youtube_transcript`  
**Purpose:** Fetches the transcript of a YouTube video (optionally in a specified language).

**Signature**

```python
# Sync
get_youtube_transcript(url: str, *, language: str | None = None) -> YTResponse

# Async
get_youtube_transcript_async(url: str, *, language: str | None = None) -> YTResponse
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `url` | `str` | — | **Required.** Full YouTube video URL. |
| `language` | `str \| None` | `None` | Optional BCP-47 language code (e.g., `"en"`). |

**Returns (`YTResponse`)**

| Field | Type | Notes |
|-------|------|-------|
| `transcript` | `str` | Full transcript text. |
| `url` | `str` | Echo of the input URL. |
| `cost` | `float \| None` | Cost charged (USD). |
| `language` | `str \| None` | Language actually used. |

**Example**

```python
yt = client.get_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ", language="en")
print(yt.transcript[:200])
```

---

### PDF Content

**Endpoint:** `POST /api/v1/get_pdf_content`  
**Purpose:** Extracts text from a public PDF URL and reports page count.

**Signature**

```python
# Sync
get_pdf_content(url: str) -> PDFResponse

# Async
get_pdf_content_async(url: str) -> PDFResponse
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `url` | `str` | — | **Required.** Public direct PDF URL. |

**Returns (`PDFResponse`)**

| Field | Type | Notes |
|-------|------|-------|
| `text` | `str` | Extracted PDF text (concatenated). |
| `pages` | `int` | Total pages. |
| `url` | `str` | Canonical URL. |
| `status_code` | `int` | HTTP status from the scrape (usually 200). |
| `cost` | `float \| None` | Cost charged (USD). |

**Example**

```python
pdf = client.get_pdf_content("https://arxiv.org/pdf/2203.15556.pdf")
print(pdf.pages, pdf.text[:300])
```

---

### Scrape

**Endpoint:** `POST /api/v1/scrape`  
**Purpose:** Scrapes a URL into one of several formats.

**Signature**

```python
# Sync
scrape(url: str, *, format: Literal['markdown','html','pdf','screenshot'] = 'markdown',
       include_images: bool = True, include_links: bool = True) -> ScraperResponse

# Async
scrape_async(url: str, *, format: Literal['markdown','html','pdf','screenshot'] = 'markdown',
             include_images: bool = True, include_links: bool = True) -> ScraperResponse
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `url` | `str` | — | **Required.** Public URL to scrape. |
| `format` | `"markdown" \| "html" \| "pdf" \| "screenshot"` | `"markdown"` | Output format. |
| `include_images` | `bool` | `True` | For markdown, inline images where possible. |
| `include_links` | `bool` | `True` | For markdown, preserve hyperlinks. |

**Returns (`ScraperResponse`)**

| Field | Type | Populated when |
|-------|------|---------------|
| `markdown` | `str` | `format='markdown'` |
| `html` | `str \| None` | `format='html'` |
| `pdf_data` | `str \| None` | `format='pdf'` — base64 PDF bytes |
| `screenshot_data` | `str \| None` | `format='screenshot'` — base64 PNG bytes |
| `url` | `str` | Always |
| `status_code` | `int` | Always |
| `cost` | `float \| None` | Always |

**Examples**

```python
# Markdown
md = client.scrape("https://example.com", format="markdown")
print(md.markdown[:300])

# HTML
html = client.scrape("https://example.com", format="html")
print(bool(html.html))

# PDF → write to disk
pdf = client.scrape("https://example.com", format="pdf")
import base64, pathlib
pathlib.Path("page.pdf").write_bytes(base64.b64decode(pdf.pdf_data or ""))

# Screenshot → write to disk
shot = client.scrape("https://example.com", format="screenshot")
pathlib.Path("screenshot.png").write_bytes(base64.b64decode(shot.screenshot_data or ""))
```

---

### Web Search

**Endpoint:** `POST /api/v1/web_search`  
**Purpose:** Direct access to vertical search indices without invoking the full Answer pipeline.

**Signature**

```python
# Sync
search_web(query: str, *, search_type: Literal['general','news','shopping','videos','images','scholar'] = 'general',
           location: str = 'us', recency: str | None = None, 
           domain_filter: list[str] | None = None) -> WebSearchResponse

# Async
search_web_async(query: str, *, search_type: Literal['general','news','shopping','videos','images','scholar'] = 'general',
                 location: str = 'us', recency: str | None = None, 
                 domain_filter: list[str] | None = None) -> WebSearchResponse
```

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | `str` | — | **Required.** The search query. |
| `search_type` | `"general" \| "news" \| "shopping" \| "videos" \| "images" \| "scholar"` | `"general"` | Search vertical. |
| `location` | `str` | `"us"` | Geo/market bias. |
| `recency` | `"hour" \| "day" \| "week" \| "month" \| "year" \| None` | `None` | Recency filter. |
| `domain_filter` | `list[str] \| None` | `None` | Include/exclude domains (prefix with `-` to exclude). |

**Returns (`WebSearchResponse`)**

| Field | Type | Notes |
|-------|------|-------|
| `results` | `list[dict]` | Items with fields appropriate to the vertical (e.g., `title`, `url`, `snippet`). |
| `cost` | `float \| None` | Cost charged (USD). Shopping has higher cost tier. |

**Examples**

```python
# General search, exclude Wikipedia
general = client.search_web("vector databases", domain_filter=["-wikipedia.org"])
print(len(general.results))

# Recent news
news = client.search_web("ai agents", search_type="news", recency="day")
print(news.results[0] if news.results else None)

# Images
images = client.search_web("james webb telescope", search_type="images")
print(images.results[:3])

    
# Scholar
scholar = client.search_web("transformer models", search_type="scholar")
print(scholar.results[0] if scholar.results else None)

# Shopping
shopping = client.search_web("iphone 17", search_type="shopping")
print(shopping.results[0] if shopping.results else None)
```

---

## Advanced Tips

* **`json_schema`**: You can pass a Python `dict`; the client serializes it for `answer_type="json"` (remember: **not** streamable).
* **Domain filters**: Include `["example.com"]`, exclude with a leading dash `["-wikipedia.org"]`.
* **Per-call overrides**: You can override `timeout` and add `headers={"X-Debug":"1"}` on any call.
* **Reusing `httpx` clients**: Inject an existing `httpx.Client`/`AsyncClient` to share connection pools across your app.
* **Context managers**: `with LLMLayerClient(...) as client:` closes owned clients automatically.

---

## Version & Changelog

**0.2.0**

* Utilities now **POST** JSON bodies: `/youtube_transcript`, `/get_pdf_content`, `/scrape`, `/web_search`.
* `scrape` unified for markdown/html/pdf/screenshot (no separate helpers).
* `web_search` returns `{ results, cost }`.
* Streaming rejects `answer_type="json"` to match server behavior; better early SSE error handling.

---

## License

MIT © 2025 LLMLayer Inc.

---

## Support

* **Issues & feature requests**: open a ticket on GitHub.
* For private support, contact **[support@llmlayer.ai](mailto:support@llmlayer.ai)**.
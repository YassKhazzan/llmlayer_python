# LLMLayer Python SDK (API v2)

> **Search → Reason → Cite** with one call.
>
> Official Python client for the **LLMLayer Web API v2** — typed models, streaming via SSE, and production‑ready ergonomics.

---

## Table of Contents

* [Overview](#overview)
* [What’s new in v2 (breaking changes)](#whats-new-in-v2-breaking-changes)
* [Installation](#installation)
* [Authentication](#authentication)
* [Quickstart](#quickstart)

  * [Synchronous](#synchronous)
  * [Asynchronous](#asynchronous)
* [Answer API](#answer-api)

  * [When to use blocking vs streaming](#when-to-use-blocking-vs-streaming)
  * [Blocking Answer — `POST /api/v2/answer`](#blocking-answer--post-apiv2answer)
  * [Streaming Answer — `POST /api/v2/answer_stream`](#streaming-answer--post-apiv2answer_stream)
  * [Request Parameters (complete reference)](#request-parameters-complete-reference)
  * [Response Shape](#response-shape)
  * [Streaming Frames](#streaming-frames)
* [Utilities](#utilities)

  * [Web Search — `POST /api/v2/web_search`](#web-search--post-apiv2web_search)
  * [Scrape (multi-format) — `POST /api/v2/scrape`](#scrape-multi-format--post-apiv2scrape)
  * [PDF Content — `POST /api/v2/get_pdf_content`](#pdf-content--post-apiv2get_pdf_content)
  * [YouTube Transcript — `POST /api/v2/youtube_transcript`](#youtube-transcript--post-apiv2youtube_transcript)
  * [Map — `POST /api/v2/map`](#map--post-apiv2map)
  * [Crawl Stream — `POST /api/v2/crawl_stream`](#crawl-stream--post-apiv2crawl_stream)
* [End‑to‑End Pipelines](#end-to-end-pipelines)

  * [Map → Crawl → Save Markdown](#map--crawl--save-markdown)
* [Advanced Usage](#advanced-usage)

  * [Configuration options](#configuration-options)
  * [Context managers](#context-managers)
  * [Injecting custom `httpx` clients / proxies / retries](#injecting-custom-httpx-clients--proxies--retries)
  * [Per‑request timeouts & headers](#per-request-timeouts--headers)
* [Errors](#errors)
* [Cost Model & Models](#cost-model--models)
* [Troubleshooting](#troubleshooting)
* [License & Support](#license--support)

---

## Overview

**LLMLayer** unifies web search, context building, and LLM reasoning behind a clean API. The Python SDK provides:

* **Answer** (blocking & streaming via SSE)
* **Vertical Web Search** (general/news/images/videos/shopping/scholar)
* **Scraping** (markdown/html/pdf/screenshot)
* **PDF** text extraction
* **YouTube** transcript + metadata
* **Site Map** discovery
* **Crawl Stream** (stream pages & artifacts; usage billed per successful page)

All endpoints use typed Pydantic models, mapped exceptions, and support both sync and async via `httpx`.

---

## What’s new in v2 (breaking changes)

* **Routes moved to `/api/v2`** for all endpoints.
* **Answer response** field renamed: `answer` (was `llm_response`).
* **Answer streaming** content frames use `{ "type": "answer", "content": "..." }` (was `type: "llm"`).
* **Scrape** accepts **`formats: List["markdown"|"html"|"screenshot"|"pdf"]`** and returns `markdown/html/pdf/screenshot`, `title`, `metadata`, and **`statusCode`**.
* **Map** response now uses **`statusCode`** (camelCase).
* **Crawl** request takes a single **`url`** (not `seeds`) and **`formats`** list; stream frames are `page`/`usage`/`done`/`error`.
* **YouTube** response includes metadata: `title`, `description`, `author`, `views`, `likes`, `date`.

---

## Installation

```bash
pip install llmlayer
# or
pipx install llmlayer
```

**Python**: 3.9+ recommended (tested 3.9–3.12). The SDK uses `httpx` under the hood.

---

## Authentication

All requests require a bearer token:

```
Authorization: Bearer YOUR_LLMLAYER_API_KEY
```

* Pass `api_key=...` to the client **or** set the environment variable `LLMLAYER_API_KEY`.
* Missing/invalid keys raise `AuthenticationError`.

> **Never embed your API key in public client code.** Run calls from trusted server code.

---

## Quickstart

### Synchronous

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()  # reads LLMLAYER_API_KEY from env

resp = client.answer(
    query="What are the latest AI breakthroughs?",
    model="openai/gpt-4o-mini",
    return_sources=True,
)
print(resp.answer)
print("sources:", len(resp.sources))
```

### Asynchronous

```python
import asyncio
from llmlayer import LLMLayerClient

async def main():
    client = LLMLayerClient()
    resp = await client.answer_async(
        query="Explain edge AI in one short paragraph",
        model="openai/gpt-4o-mini",
    )
    print(resp.answer)

asyncio.run(main())
```

---

## Answer API

### When to use blocking vs streaming

* **Blocking** (`POST /api/v2/answer`): you need the complete answer before proceeding or you want **structured JSON** (`answer_type='json'` with `json_schema`).
* **Streaming** (`POST /api/v2/answer_stream`): chat UIs, progressive rendering, lower perceived latency.

> **Note:** Streaming **does not** support `answer_type='json'`. Use blocking for structured output.

### Blocking Answer — `POST /api/v2/answer`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
resp = client.answer(
    query="Explain quantum computing in simple terms",
    model="openai/gpt-4o-mini",
    temperature=0.7,
    max_tokens=1000,
    return_sources=True,
)
print(resp.answer)
print("sources:", len(resp.sources))
print("total cost =", (resp.model_cost or 0) + (resp.llmlayer_cost or 0))
```

**Structured JSON output**

```python
import json
from llmlayer import LLMLayerClient

schema = {
    "type": "object",
    "properties": {
        "topic":   {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["topic", "bullets"],
}

client = LLMLayerClient()
resp = client.answer(
    query="Return a topic and 3 bullets about transformers",
    model="openai/gpt-4o",
    answer_type="json",
    json_schema=schema,   # dict allowed; client serializes to JSON string
)

data = resp.answer if isinstance(resp.answer, dict) else json.loads(resp.answer)
print(data["topic"], len(data["bullets"]))
```

### Streaming Answer — `POST /api/v2/answer_stream`

The response is **Server‑Sent Events** (SSE) with **data‑only** JSON frames that include a `type` discriminator.

**Sync streaming**

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
text = []
for event in client.stream_answer(
    query="History of the Internet in 5 lines",
    model="groq/llama-3.3-70b-versatile",
    return_sources=True,
):
    t = event.get("type")
    if t == "answer":            # v2: 'answer' (not 'llm')
        chunk = event.get("content", "")
        print(chunk, end="")
        text.append(chunk)
    elif t == "sources":
        print("\n[SOURCES]", len(event.get("data", [])))
    elif t == "images":
        print("\n[IMAGES]", len(event.get("data", [])))
    elif t == "usage":
        print("\n[USAGE]", event)
    elif t == "done":
        print("\n✓ finished in", event.get("response_time"), "s")
```

**Async streaming**

```python
import asyncio
from llmlayer import LLMLayerClient

async def main():
    client = LLMLayerClient()
    async for event in client.stream_answer_async(
        query="Three concise benefits of edge AI",
        model="openai/gpt-4o-mini",
        return_sources=True,
    ):
        if event.get("type") == "answer":
            print(event.get("content", ""), end="")

asyncio.run(main())
```

---

### Request Parameters (complete reference)

You may use either **snake_case** or the usual keyword names shown below.

| Param                 | Type                                                    | Required | Default      | Description                                                                                                                                                                            |                                                           |                                                                         |
| --------------------- | ------------------------------------------------------- | :------: | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------- |
| `query`               | `str`                                                   |     ✅    | —            | The question/instruction.                                                                                                                                                              |                                                           |                                                                         |
| `model`               | `str`                                                   |     ✅    | —            | LLM id (e.g., `openai/gpt-4o-mini`, `openai/gpt-4.1-mini`, `anthropic/claude-sonnet-4`, `groq/llama-3.3-70b-versatile`, `deepseek/deepseek-reasoner`). Unsupported → `InvalidRequest`. |                                                           |                                                                         |
| `provider_key`        | `str`                                                   |          | —            | Upstream provider key. If set, provider usage is billed to **your** account and `model_cost` becomes `None`.                                                                           |                                                           |                                                                         |
| `location`            | `str`                                                   |          | `'us'`       | Market/geo bias for search (country code).                                                                                                                                             |                                                           |                                                                         |
| `system_prompt`       | `str                                                    |   None`  |              | `None`                                                                                                                                                                                 | Override system prompt (non‑JSON answers).                |                                                                         |
| `response_language`   | `str`                                                   |          | `'auto'`     | Output language; `'auto'` infers from query.                                                                                                                                           |                                                           |                                                                         |
| `answer_type`         | `Literal['markdown','html','json']`                     |          | `'markdown'` | Output format. If `'json'`, you **must** supply `json_schema`. Not supported by streaming.                                                                                             |                                                           |                                                                         |
| `search_type`         | `Literal['general','news']`                             |          | `'general'`  | Search vertical. Use `search_web` for other verticals.                                                                                                                                 |                                                           |                                                                         |
| `json_schema`         | `str                                                    |   dict   | None`        |                                                                                                                                                                                        | `None`                                                    | Required when `answer_type='json'`. Dicts are serialized automatically. |
| `citations`           | `bool`                                                  |          | `False`      | Embed inline citation markers.                                                                                                                                                         |                                                           |                                                                         |
| `return_sources`      | `bool`                                                  |          | `False`      | Include aggregated `sources` and emit a `sources` frame in streaming.                                                                                                                  |                                                           |                                                                         |
| `return_images`       | `bool`                                                  |          | `False`      | Include image results (adds a small LLMLayer fee).                                                                                                                                     |                                                           |                                                                         |
| `date_filter`         | `Literal['anytime','hour','day','week','month','year']` |          | `'anytime'`  | Recency filter.                                                                                                                                                                        |                                                           |                                                                         |
| `max_tokens`          | `int`                                                   |          | `1500`       | Max LLM output tokens.                                                                                                                                                                 |                                                           |                                                                         |
| `temperature`         | `float`                                                 |          | `0.7`        | Sampling temperature (0.0–2.0).                                                                                                                                                        |                                                           |                                                                         |
| `domain_filter`       | `list[str]                                              |   None`  |              | `None`                                                                                                                                                                                 | Include domains normally; **exclude** with `-domain.com`. |                                                                         |
| `max_queries`         | `int`                                                   |          | `1`          | Number of search sub‑queries (1–5). Each adds a small LLMLayer fee and may improve coverage.                                                                                           |                                                           |                                                                         |
| `search_context_size` | `Literal['low','medium','high']`                        |          | `'medium'`   | How much context to feed the LLM.                                                                                                                                                      |                                                           |                                                                         |

**Supported locations (examples):**

```
us, ca, uk, mx, es, de, fr, pt, be, nl, ch, no, se, at, dk, fi, tr, it, pl, ru, za, ae, sa, ar, br, au, cn, kr, jp, in, ps, kw, om, qa, il, ma, eg, ir, ly, ye, id, pk, bd, my, ph, th, vn
```

---

### Response Shape

`AnswerResponse` (Pydantic model)

```python
{
  "answer": str | dict,            # markdown/html string, or dict for JSON answers
  "response_time": float | str,    # e.g. "1.23"
  "input_tokens": int,
  "output_tokens": int,
  "sources": list[dict],           # present when return_sources=True
  "images": list[dict],            # present when return_images=True
  "model_cost": float | None,      # None when using provider_key
  "llmlayer_cost": float | None
}
```

---

### Streaming Frames

The server emits JSON frames over SSE with a `type` discriminator:

| `type`    | Payload Keys                                                                                   | Meaning                     |
| --------- | ---------------------------------------------------------------------------------------------- | --------------------------- |
| `answer`  | `content: str`                                                                                 | Partial LLM text chunk (v2) |
| `sources` | `data: list[dict]`                                                                             | Aggregated sources          |
| `images`  | `data: list[dict]`                                                                             | Relevant images             |
| `usage`   | `input_tokens: int`, `output_tokens: int`, `model_cost: float \| None`, `llmlayer_cost: float` | Token/cost summary          |
| `done`    | `response_time: str`                                                                           | Completion                  |
| `error`   | `error: str`                                                                                   | Error frame (raised by SDK) |

> The client handles multi‑line `data:` frames and early error frames automatically.

---


## Models & Pricing

Prices are USD per **1M tokens** (input/output). LLMLayer passes through provider pricing with **no markup**. Your total cost = provider usage + LLMLayer fee (see [Cost Model](#cost-model)). Availability may vary by region/account.

### OpenAI

| Model                 | Input ($/M) | Output ($/M) | Best For                     |
| --------------------- | ----------: | -----------: | ---------------------------- |
| `openai/gpt-5`        |       $1.25 |       $10.00 | Complex reasoning & analysis |
| `openai/gpt-5-mini`   |       $0.25 |        $2.00 | Cost-effective reasoning     |
| `openai/gpt-5-nano`   |       $0.05 |        $0.40 | Balanced performance         |
| `openai/o3`           |       $2.00 |        $8.00 | Complex reasoning & analysis |
| `openai/o3-mini`      |       $1.10 |        $4.40 | Cost-effective reasoning     |
| `openai/o4-mini`      |       $1.10 |        $4.40 | Balanced performance         |
| `openai/gpt-4.1`      |       $2.00 |        $8.00 | Advanced tasks               |
| `openai/gpt-4.1-mini` |       $0.40 |        $1.60 | Efficient advanced tasks     |
| `openai/gpt-4o`       |       $2.50 |       $10.00 | Multimodal & complex queries |
| `openai/gpt-4o-mini`  |       $0.15 |        $0.60 | Fast, affordable searches    |

### Groq

| Model                                     | Input ($/M) | Output ($/M) | Best For                 |
| ----------------------------------------- | ----------: | -----------: | ------------------------ |
| `groq/openai-gpt-oss-120b`                |       $0.15 |        $0.75 | High-performance search  |
| `groq/openai-gpt-oss-20b`                 |       $0.10 |        $0.50 | Budget-friendly quality  |
| `groq/kimi-k2`                            |       $1.00 |        $3.00 | High-performance search  |
| `groq/qwen3-32b`                          |       $0.29 |        $0.59 | Budget-friendly quality  |
| `groq/llama-3.3-70b-versatile`            |       $0.59 |        $0.79 | Versatile applications   |
| `groq/deepseek-r1-distill-llama-70b`      |       $0.75 |        $0.99 | Deep reasoning tasks     |
| `groq/llama-4-maverick-17b-128e-instruct` |       $0.20 |        $0.60 | Fast, efficient searches |

### Anthropic

| Model                       | Input ($/M) | Output ($/M) | Best For                                        |
| --------------------------- | ----------: | -----------: | ----------------------------------------------- |
| `anthropic/claude-sonnet-4` |       $3.00 |       $15.00 | Highly creative writing & intelligent responses |

### DeepSeek

| Model                        | Input ($/M) | Output ($/M) | Best For             |
| ---------------------------- | ----------: | -----------: | -------------------- |
| `deepseek/deepseek-chat`     |       $0.27 |        $1.10 | General purpose chat |
| `deepseek/deepseek-reasoner` |       $0.55 |        $2.19 | Complex reasoning    |

#### Choosing a model

* **Fast & economical:** `openai/gpt-4o-mini`, `groq/openai-gpt-oss-20b`
* **Balanced quality:** `openai/gpt-4.1-mini`, `groq/llama-3.3-70b-versatile`
* **Premium reasoning:** `openai/gpt-5`, `openai/o3`, `anthropic/claude-sonnet-4`, `deepseek/deepseek-reasoner`
* **Multimodal:** `openai/gpt-4o` / `openai/gpt-4o-mini`

---

## Cost Model

**Zero‑markup policy.** Provider usage is passed through at cost. LLMLayer charges a small infrastructure fee per search.

```
Total Cost = ($0.004 × max_queries) + (Input Tokens × Model Input Price) + (Output Tokens × Model Output Price)
           + [$0.001 if return_images = true]
```

Use response fields to monitor cost: `model_cost`, `llmlayer_cost`, `input_tokens`, `output_tokens`.

---

## Utilities

### Web Search — `POST /api/v2/web_search`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
res = client.search_web(
    query="ai agents",
    search_type="news",         # 'general' | 'news' | 'shopping' | 'videos' | 'images' | 'scholar'
    location="us",
    recency="day",
    domain_filter=["-reddit.com", "reuters.com"],
)
print(len(res.results), res.cost)

# general search =========================
response  = await client.search_web_async(
        query="What is edge AI?",
        location="us",
        search_type="general"
)
for res in response.results:
    print('----------------')
    print("URL: ", res.get('link', ''))
    print("TITLE : ",res.get('title'),'')
    print("SNIPPET ", res.get('snippet'),'')

# news search ==========================
response  = await client.search_web_async(
        query="Artificial Intelligence",
        location="us",
        search_type="news"
)

for res in response.results:
    print('----------------')
    print("URL: ", res.get('link', ''))
    print("TITLE : ",res.get('title'),'')
    print("SNIPPET ", res.get('snippet'),'')
    print("DATE", res.get('date',''))
    print("SOURCE", res.get('source',''))
    print("IMAGE", res.get('imageUrl',''))

# shopping search =======================
response  = await client.search_web_async(
        query="Apple iPhone 15",
        location="us",
        search_type="shopping"
)

for res in response.results:
    print('----------------')
    print("URL: ", res.get('link', ''))
    print("TITLE : ",res.get('title'),'')
    print('SOURCE :', res.get('source',''))
    print("PRICE", res.get('price',''))
    print("RATING", res.get('rating',''))
    print("RATING COUNT", res.get('ratingCount',''))
    print("PRODUCTID ", res.get('productId',''))
    print("IMAGE", res.get('imageUrl',''))

# videos search ======================
response  = await client.search_web_async(
        query="Artificial Intelligence",
        location="us",
        search_type="videos"
)

for res in response.results:
    print('----------------')
    print("URL: ", res.get('link', ''))
    print("TITLE : ",res.get('title'),'')
    print("SNIPPET :", res.get('snippet'),'')
    print("DATE : ", res.get('date',''))
    print("SOURCE", res.get('source',''))
    print('CHANNEL :', res.get('channel',''))
    print("IMAGE", res.get('imageUrl',''))
    print("DURATION", res.get('duration',''))
    
# images search ===============================
response  = await client.search_web_async(
        query="Artificial Intelligence",
        location="us",
        search_type="images"
)

for res in response.results:
    print('----------------')
    print("URL: ", res.get('link', ''))
    print("TITLE : ",res.get('title'),'')
    print("SOURCE", res.get('source',''))
    print("IMAGE", res.get('imageUrl',''))
    print("THUMBNAIL", res.get('thumbnailUrl',''))
    print("HEIGHT", res.get('height',''))
    print("WIDTH", res.get('width',''))    

```

### Scrape (multi-format) — `POST /api/v2/scrape`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()

# Request multiple outputs in one call
r = client.scrape(
    url="https://example.com",
    formats=["markdown", "html"], # can also request "screenshot"
    include_images=True,
    include_links=True,
)
print("status:", r.statusCode, "cost:", r.cost)
print("md len:", len(r.markdown), "html?", bool(r.html), "pdf?", bool(r.pdf), "shot?", bool(r.screenshot))
```

### PDF Content — `POST /api/v2/get_pdf_content`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
pdf = client.get_pdf_content("https://arxiv.org/pdf/1706.03762.pdf")
print("pages:", pdf.pages, "status:", pdf.status_code, "cost:", pdf.cost)
print("preview:", pdf.text[:200])
```

### YouTube Transcript — `POST /api/v2/youtube_transcript`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
yt = client.get_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ", language="en")
print(yt.title, yt.author, yt.views, yt.date,yt.description,yt.likes)
print(yt.transcript[:200])
```

### Map — `POST /api/v2/map`

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()
mp = client.map("https://docs.llmlayer.ai", limit=100, include_subdomains=False)
print("status:", mp.statusCode, "links:", len(mp.links), "cost:", mp.cost)
print("first:", mp.links[0].url, mp.links[0].title)

for link in mp.links:
    print('----------------')
    print("URL: ", link.url)
    print("TITLE : ",link.title)
```

### Crawl Stream — `POST /api/v2/crawl_stream`

Request a crawl of a single seed **`url`** and choose the artifacts you want per page.

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient()

for f in client.crawl_stream(
    url="https://docs.llmlayer.ai",
    max_pages=5,
    max_depth=1,
    timeout_seconds=30,
    formats=["markdown"],
    main_content_only=False,
    advanced_proxy=False,
):
    if f.get("type") == "page":
        p = f.get("page", {})
        if p.get("success"):
            markdown = p.get("markdown") or ""
            print(f"Markdown length: {len(markdown)}")
            print(markdown[:500])
            print("ok:", p.get("final_url"), "md_len:", len(p.get("markdown") or ""))
        else:
            print("fail:", p.get("final_url"), "err:", p.get("error"))
    elif f.get("type") == "usage":
        print("billed:", f.get("billed_count"), "cost:", f.get("cost"))
    elif f.get("type") == "done":
        print("done in", f.get("response_time"), "s")
```

> `max_pages` is an **upper bound** (not a guarantee). You may receive fewer pages if the site is small, the time budget is hit, pages fail, or duplicates are deduped. Only **successful** pages are billed.

---

## End‑to‑End Pipelines

### Map → Crawl → Save Markdown

```python
import pathlib
from llmlayer import LLMLayerClient

client = LLMLayerClient()

# 1) Map
m = client.map("https://docs.llmlayer.ai", limit=200)
seeds = [l.url for l in m.links][:50]

# 2) Crawl (pick the top seed or a section)
out_dir = pathlib.Path("crawl_out"); out_dir.mkdir(exist_ok=True)
for f in client.crawl_stream(url=seeds[0], max_pages=15, max_depth=2, timeout_seconds=60, formats=["markdown"]):
    if f.get("type") == "page":
        p = f.get("page", {})
        if p.get("success") and p.get("markdown"):
            name = (p.get("title") or p.get("final_url") or "page").split("/")[-1][:64]
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
            (out_dir / f"{safe}.md").write_text(p["markdown"], encoding="utf-8")
```

---

## Advanced Usage

### Configuration options

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient(
    api_key="sk-...",                         # or via LLMLAYER_API_KEY env var
    base_url="https://api.llmlayer.dev",      # override if self-hosting / staging
    timeout=60.0,                               # seconds (float or httpx.Timeout)
)
```

### Context managers

```python
from llmlayer import LLMLayerClient

with LLMLayerClient() as client:
    res = client.answer(query="hi", model="openai/gpt-4o-mini")
    print(res.answer)

# Async context manager
async def main():
    async with LLMLayerClient() as client:
        res = await client.answer_async(query="hi", model="openai/gpt-4o-mini")
```

### Injecting custom `httpx` clients / proxies / retries

```python
import httpx
from llmlayer import LLMLayerClient

transport = httpx.HTTPTransport(retries=3)
session = httpx.Client(transport=transport, timeout=30)
client = LLMLayerClient(client=session)
```

> The SDK merges required headers (Authorization, User‑Agent) into injected clients.

### Per‑request timeouts & headers

Every method accepts optional `timeout=` and `headers=` overrides:

```python
resp = client.answer(
    query="hi",
    model="openai/gpt-4o-mini",
    timeout=15.0,
    headers={"X-Debug": "1"},
)
```

---

## Errors

All exceptions extend `LLMLayerError`:

* `InvalidRequest` — 400 (missing/invalid params; early SSE errors like `missing_model`)
* `AuthenticationError` — 401/403 (missing/invalid LLMLayer key; provider auth issues)
* `RateLimitError` — 429
* `ProviderError` — upstream LLM provider errors
* `InternalServerError` — 5xx

**Server envelope example** (the client unwraps `detail` automatically):

```json
{
  "detail": {
    "error_type": "validation_error",
    "error_code": "missing_query",
    "message": "Query parameter cannot be empty"
  }
}
```

---

## Cost Model & Models

**Zero‑markup policy.** Provider usage is passed through at cost. LLMLayer charges a small infrastructure fee per search.

```
Total Cost = ($0.004 × max_queries) + (Input Tokens × Model Input Price) + (Output Tokens × Model Output Price)
           + [$0.001 if return_images = true]
```

Model availability & pricing depend on your account/region. See the docs for the latest allow‑list and price table.

---

## Troubleshooting

* **`answer_type='json'` with streaming** → not supported. Use blocking `answer()`.
* **SSL/Connect errors** → configure corporate proxies on your injected `httpx.Client`.
* **Event loop errors** in notebooks → run with `asyncio.run(...)` or use a fresh kernel.
* **Large base64 payloads** (`pdf`/`screenshot`) → write to disk; avoid keeping big blobs in memory.

---

## License & Support

**License:** MIT
**Issues & feature requests:** GitHub Issues
**Private support:** [support@llmlayer.ai](mailto:support@llmlayer.ai)

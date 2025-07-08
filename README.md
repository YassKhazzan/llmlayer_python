# LLMLayer Python SDK

![PyPI](https://img.shields.io/pypi/v/llmlayer?color=blue) ![Python](https://img.shields.io/pypi/pyversions/llmlayer.svg) ![CI](https://github.com/your-org/llmlayer-sdk/actions/workflows/ci.yml/badge.svg)

> **Search – Reason – Cite** with one function call.
>
> This library is the *official* Python interface for the [LLMLayer Search & Answer API](https://llmlayer.ai). It lets you send queries to your self‑hosted or cloud instance, receive fully‑reasoned answers, and stream intermediate content in real‑time.

---

## ✨ Features

|                            |                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------ |
| 🗂 **Multi‑provider**      | Seamlessly speak to OpenAI, Anthropic (Claude), Gemini, DeepSeek, or Groq models ✨   |
| 🔄 **Sync & Async**        | Choose the style that fits your stack – both are first‑class citizens                |
| ⏱ **Streaming**            | Get partial chunks via Server‑Sent Events; perfect for chat UIs                      |
| 🛡 **Elegant error model** | `InvalidRequest`, `ProviderError`, `RateLimitError`, … – catch exactly what you need |
| 🔌 **Dependency‑light**    | Only `httpx` and `pydantic` at runtime                                               |
| 🧪 **Dev‑friendly**        | Drop‑in scripts (`test.py`, `test_stream.py`) and local import support               |

---

\## Table of Contents

* [Installation](#installation)
* [Quick Start](#quick-start)

  * [Sync call](#sync-call)
  * [Async call](#async-call)
  * [Streaming](#streaming)
* [Configuration](#configuration)

  * [Environment Variables](#environment-variables)
* [API Reference](#api-reference)

  * [`LLMLayerClient`](#llmlayerclient)
  * [Data Models](#data-models)
* [Error Handling](#error-handling)
* [Advanced Usage](#advanced-usage)

  * [Re‑using `httpx` clients](#re-using-httpx-clients)
  * [Proxies & Timeouts](#proxies--timeouts)
* [Development](#development)
* [License](#license)

---

## Installation

```bash
pip install llmlayer
```

> **Python ≥ 3.9** is required.

---

## Quick Start

###  Sync call

```python
from llmlayer import LLMLayerClient

client = LLMLayerClient(
    api_key="<LLMLAYER_KEY>",          # Bearer token
    provider="openai",                  # one of openai|anthropic|gemini|groq|deepseek
    provider_key="<PROVIDER_API_KEY>", # e.g. your OpenAI key
)

resp = client.search(
    query="Why is the sky blue?",
    model="gpt-4.1-mini",
    return_sources=True,
)

print(resp.llm_response)
for src in resp.sources:
    print(src["title"], src["url"])
```

###  Async call

```python
import asyncio
from llmlayer_sdk import LLMLayerClient

async def main():
    client = LLMLayerClient(
        api_key="<LLMLAYER_KEY>",
        provider="anthropic",
        provider_key="<CLAUDE_KEY>",
        base_url="https://api.llmlayer.dev",
    )
    resp = await client.asearch(
        query="List three applications of quantum tunnelling",
        model="claude-3-sonnet-20240229",
    )
    print(resp.llm_response)

asyncio.run(main())
```

###  Streaming

```python
from llmlayer_sdk import LLMLayerClient

client = LLMLayerClient(
    api_key="LLMLAYER_API_KEY",
    provider="gemini",
    provider_key="<GEMINI_KEY>",
)

for event in client.search_stream(
    query="Explain brown dwarfs in two paragraphs",
    model="gemini-2.5-pro",
    return_sources=True,
):
    if event["type"] == "llm":
        print(event["content"], end="", flush=True)
    elif event["type"] == "sources":
        print("\nSources:", event["data"])
    elif event["type"] == "done":
        print(f"\n✓ finished in {event['response_time']} s")
```

---

##  Configuration

###  Environment Variables

| Variable             | Purpose                                        | Fallback if unset                       |
| -------------------- | ---------------------------------------------- | --------------------------------------- |
| `LLMLAYER_API_KEY`   | Bearer token sent as `Authorization: Bearer …` | *required*                              |
| `LLMLAYER_PROVIDER`  | Default provider (`openai`, `anthropic`, …)    | `openai`                                |
| `<PROVIDER>_API_KEY` | Provider‑specific key, e.g. `OPENAI_API_KEY`   | *required unless passed to constructor* |

All constructor args override env vars.

---

##  API Reference

###  `LLMLayerClient`

| Parameter      | Type                     | Default  | Description                       |
| -------------- | ------------------------ |----------| --------------------------------- |
| `api_key`      | `str`                    |  —       | LLMLayer bearer token (mandatory) |
| `provider`     | `str`                    | `openai` | Upstream LLM provider name        |
| `provider_key` | `str`                    |  —       | Provider API key                  |
| `timeout`      | `float \| httpx.Timeout` | `60.0`   | Request timeout                   |
| `client`       | `httpx.Client \| None`   | `None`   | Inject your own `httpx` client    |

####  Methods

| Method                     | Description                                |
| -------------------------- | ------------------------------------------ |
| `search(**params)`         | Blocking call → `SimplifiedSearchResponse` |
| `search_stream(**params)`  | Generator yielding SSE events              |
| `asearch(**params)`        | `async` version of `search`                |
| `asearch_stream(**params)` | `async` generator                          |

---


###  Search parameters

Below keys map 1‑to‑1 to the backend’s `SearchRequest` schema.

| Name                | Type                             | Default     | Notes                                                              |
| ------------------- | -------------------------------- | ----------- |--------------------------------------------------------------------|
| `query`             | `str`                            | —           | User question / search prompt                                      |
| `model`             | `str`                            | —           | Provider model name (`gpt-4o-mini`, `claude‑3‑sonnet‑20240229`, …) |
| `date_context`      | `str?`                           | `None`      | Inject a date string the prompt can reference                      |
| `location`          | `str`                            | `"us"`      | Geographical search bias                                           |
| `system_prompt`     | `str?`                           |  —          | Override LLMLayer’s default prompt                                 |
| `response_language` | `str`                            | `"auto"`    | `"auto"` to detect user language                                   |
| `answer_type`       | `"markdown" \| "html" \| "json"` | `markdown`  | Output format                                                      |
| `search_type`       | `"general" \| "news"`            | `general`   | Vertical search bias                                               |
| `json_schema`       | `str?`                           |  —          | Required when `answer_type = json`                                 |
| `citations`         | `bool`                           | `False`     | Embed `[n]` citations into answer                                  |
| `return_sources`    | `bool`                           | `False`     | Include `sources` in response                                      |
| `return_images`     | `bool`                           | `False`     | Include `images` (if available)                                    |
| `date_filter`       | `str`                            | `"anytime"` | `hour`, `day`, `week`, `month`, `year`                              |
| `max_tokens`        | `int`                            | `1500`      | LLM max tokens                                                     |
| `temperature`       | `float`                          | `0.7`       | Adjust creativity                                                  |
| `domain_filter`     | `List[str]?`                     |  —          | Restrict organic search domains                                    |
| `max_queries`       | `int`                            | `1`         | How many search queries LLMLayer should generate                   |

---

###  Data Models

```python
from llmlayer_sdk.models import SearchRequest, SimplifiedSearchResponse
```

Both are `pydantic.BaseModel` subclasses – perfect for validation, FastAPI, or serialization.

---

##  Error Handling

All exceptions inherit from `llmlayer_sdk.exceptions.LLMLayerError`.

| Class                 | Raised When                                    |
| --------------------- | ---------------------------------------------- |
| `InvalidRequest`      | Bad request parameters (400)                   |
| `AuthenticationError` | Missing/invalid LLMLayer or provider key (401) |
| `RateLimitError`      | Provider 429 errors                            |
| `ProviderError`       | Generic provider‑side issue (≥400)             |
| `InternalServerError` | LLMLayer 5xx                                   |

Example:

```python
from llmlayer_sdk.exceptions import RateLimitError

try:
    resp = client.search(...)
except RateLimitError:
    backoff_and_retry()
```

---

##  Advanced Usage

###  Re‑using `httpx` clients

```python
import httpx
from llmlayer_sdk import LLMLayerClient

shared = httpx.Client(http2=True, timeout=60)
client = LLMLayerClient(
    api_key="...",
    provider="openai",
    provider_key="...",
    client=shared,
)
```

###  Proxies & Timeouts

```python
transport = httpx.HTTPTransport(proxy="https://proxy.corp:3128")
custom = httpx.Client(timeout=10, transport=transport)
client = LLMLayerClient(..., client=custom)
```

---



##  License

MIT © 2025 LLMLayer Inc.  Feel free to copy, modify, and distribute.

from __future__ import annotations

from typing import List, Optional, Union, Literal, Dict, Any
from pydantic import BaseModel, Field, HttpUrl

# ================================
# Core Answer API (v2)
# ================================

class SearchRequest(BaseModel):
    # REQUIRED
    query: str
    model: str

    # Backend fields
    provider_key: Optional[str] = None
    location: str = "us"
    system_prompt: Optional[str] = None
    response_language: str = "auto"
    answer_type: Literal["markdown", "html", "json"] = "markdown"
    search_type: Literal["general", "news"] = "general"
    # Backend expects string; client may serialize dict for convenience
    json_schema: Optional[Union[str, Dict[str, Any]]] = None

    citations: bool = False
    return_sources: bool = False
    return_images: bool = False

    date_filter: Literal["hour","day","week","month","year","anytime"] = "anytime"           # "hour" | "day" | "week" | "month" | "year" | "anytime"
    max_tokens: int = 1500
    temperature: float = 0.7
    domain_filter: Optional[List[str]] = None
    max_queries: int = 1
    search_context_size: Literal["low","medium","high"] = "medium"


class AnswerResponse(BaseModel):
    # v2 returns 'answer' instead of 'llm_response'
    answer: Union[str, Dict[str, Any]]
    response_time: Union[float, str]
    input_tokens: int
    output_tokens: int
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    model_cost: Optional[float] = None
    llmlayer_cost: Optional[float] = None


# ================================
# Utilities — YouTube Transcript (v2 adds metadata)
# ================================

class YTRequest(BaseModel):
    url: str
    language: Optional[str] = None


class YTResponse(BaseModel):
    transcript: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    date: Optional[str] = None
    cost: Optional[float] = None
    language: Optional[str] = None


# ================================
# Utilities — PDF Content
# ================================

class PDFRequest(BaseModel):
    url: str


class PDFResponse(BaseModel):
    text: str
    pages: Optional[int]
    url: str
    statusCode: Optional[int]
    cost: Optional[float] = None


# ================================
# Utilities — Scrape (v2: multi-format request & fields)
# ================================

class ScrapeRequest(BaseModel):
    url: str
    formats: List[Literal["markdown", "html", "screenshot", "pdf"]]
    include_images: bool = True
    include_links: bool = True
    advanced_proxy: Optional[bool] = False
    main_content_only: Optional[bool] = False


class ScraperResponse(BaseModel):
    markdown: Optional[str] = None
    html: Optional[str] = None
    pdf: Optional[str] = None          # base64 encoded
    screenshot: Optional[str] = None   # base64 encoded
    url: str
    title: Optional[str] = None
    statusCode: int                    # v2 uses camelCase
    cost: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


# ================================
# Utilities — Web Search
# ================================

class WebSearchRequest(BaseModel):
    query: str
    search_type: Literal["general", "news", "shopping", "videos", "images", "scholar"] = "general"
    location: str = "us"
    recency: Optional[str] = None
    domain_filter: Optional[List[str]] = None


class WebSearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    cost: Optional[float] = None


# ================================
# Map endpoint (v2: statusCode)
# ================================

class MapRequest(BaseModel):
    url: HttpUrl
    ignoreSitemap: bool = False
    includeSubdomains: bool = False
    search: Optional[str] = None
    limit: int = 5000
    timeout: Optional[int] = 45000  # milliseconds


class MapLink(BaseModel):
    url: HttpUrl
    title: str


class MapResponse(BaseModel):
    links: List[MapLink]
    statusCode: int
    cost: Optional[float] = None


# ================================
# Crawl (v2 request + event stream frames)
# ================================

class CrawlRequest(BaseModel):
    url: HttpUrl
    max_pages: int = 25
    max_depth: int = 2
    timeout: Optional[float] = 60.0
    include_subdomains: bool = False
    include_links: bool = True
    include_images: bool = True
    formats: List[Literal["markdown", "html", "screenshot", "pdf"]] = ["markdown"]
    advanced_proxy: Optional[bool] = False
    main_content_only: Optional[bool] = False


# Optional JSON response models if you later expose a non-streaming crawl endpoint:

class CrawlResultItem(BaseModel):
    requested_url: str
    final_url: str
    title: str
    hash_sha256: str
    markdown: Optional[str] = None
    html: Optional[str] = None
    screenshot: Optional[str] = None  # base64
    pdf: Optional[str] = None         # base64
    success: Optional[bool] = None
    error: Optional[str] = None


class CrawlResponse(BaseModel):
    seeds: List[str]
    fetched: int
    visited: int
    max_pages: int
    max_depth: int
    results: List[CrawlResultItem]
    graph: Dict[str, List[str]]
    errors: List[Dict[str, Any]]
    billing: Dict[str, Any]
    partial: Optional[bool] = None
    status_code: int
    cost: Optional[float] = None

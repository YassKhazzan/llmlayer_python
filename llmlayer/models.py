from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field


# ================================
# Core Search API
# ================================

class SearchRequest(BaseModel):
    # REQUIRED
    query: str
    model: str
    # Backend fields (kept as plain strings for forward-compat)
    provider_key: Optional[str] = None
    location: str = "us"
    system_prompt: Optional[str] = None
    response_language: str = "auto"
    answer_type: str = "markdown"          # "markdown" | "html" | "json"
    search_type: str = "general"            # e.g. "general", "news"
    json_schema: Optional[Union[str, dict]] = None  # dict allowed; client will JSON-serialize
    citations: bool = False
    return_sources: bool = False
    return_images: bool = False
    date_filter: str = "anytime"            # "hour" | "day" | "week" | "month" | "year" | "anytime"
    max_tokens: int = 1500
    temperature: float = 0.7
    domain_filter: Optional[List[str]] = None
    max_queries: int = 1
    search_context_size: str = "medium"     # passthrough to backend


class SimplifiedSearchResponse(BaseModel):
    llm_response: Union[str, dict]
    # Server returns formatted string like "1.23"; accept float too
    response_time: Union[float, str]
    input_tokens: int
    output_tokens: int
    sources: List[dict] = Field(default_factory=list)
    images: List[dict] = Field(default_factory=list)
    model_cost: Optional[float] = None
    llmlayer_cost: Optional[float] = None


# ================================
# Utilities — YouTube Transcript
# ================================

class YTRequest(BaseModel):
    url: str
    language: Optional[str] = None


class YTResponse(BaseModel):
    transcript: str
    url: str
    cost: Optional[float] = None
    language: Optional[str] = None


# ================================
# Utilities — PDF Content
# ================================

class PDFRequest(BaseModel):
    url: str


class PDFResponse(BaseModel):
    text: str
    pages: int
    url: str
    status_code: int
    cost: Optional[float] = None


# ================================
# Utilities — Scrape (markdown/html/pdf/screenshot)
# ================================

class ScrapeRequest(BaseModel):
    url: str
    include_images: bool = True
    include_links: bool = True
    format: Literal["markdown", "html", "screenshot", "pdf"] = "markdown"


class ScraperResponse(BaseModel):
    markdown: str
    html: Optional[str] = None
    pdf_data: Optional[str] = None         # base64 encoded
    screenshot_data: Optional[str] = None  # base64 encoded
    url: str
    status_code: int
    cost: Optional[float] = None


# ================================
# Utilities — Web Search
# ================================

class WebSearchRequest(BaseModel):
    query: str
    search_type: Literal["general", "news", "shopping", "videos", "images", "scholar"] = "general"
    location: str = "us"
    recency: Optional[str] = None          # "hour" | "day" | "week" | "month" | "year"
    domain_filter: Optional[List[str]] = None  # e.g., ["example.com", "-blocked.com"]


class WebSearchResponse(BaseModel):
    results: List[dict]
    cost: Optional[float] = None

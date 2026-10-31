"""Data models for News MCP Server."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class NewsCategory(str, Enum):
    ALL = "all"
    FINANCE = "finance"
    INDUSTRY = "industry"
    BUSINESS = "business"
    TECH = "tech"
    AI = "ai"
    CRYPTO = "crypto"
    ENERGY = "energy"
    HEALTHCARE = "healthcare"
    AUTOMOTIVE = "automotive"
    WORLD = "world"
    SCIENCE = "science"


class NewsArticle(BaseModel):
    title: str = Field(..., description="Headline of the article")
    url: str = Field(..., description="Link to original article")
    source: str = Field(..., description="Name of the news source or publisher")
    summary: Optional[str] = Field(default=None, description="Short snippet or summary of the article")
    published_at: Optional[str] = Field(default=None, description="Publication timestamp or date string")
    category: Optional[str] = Field(default="general", description="Category or industry sector of the article")
    author: Optional[str] = Field(default=None, description="Author if available")


class NewsResponse(BaseModel):
    category: str = Field(default="all", description="Query category or sector")
    query: Optional[str] = Field(default=None, description="Search query keyword if applied")
    count: int = Field(..., description="Number of articles returned")
    articles: List[NewsArticle] = Field(default_factory=list, description="List of articles")

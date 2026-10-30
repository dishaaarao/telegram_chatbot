"""News MCP Server.

Provides Model Context Protocol (MCP) tools for fetching, searching,
and retrieving current news articles across diverse global and tech sources.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from .models import NewsCategory, NewsResponse
from .sources import NewsAggregator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("news-mcp-server")

# Instantiate MCPServer
mcp = MCPServer(name="NewsAggregatorServer")
aggregator = NewsAggregator()


@mcp.tool(
    name="get_top_news",
    description="Fetch current top news headlines from multiple sources across categories: tech, ai, business, world, science, or all.",
)
async def get_top_news(category: str = "all", limit: int = 10) -> str:
    """Fetch top news articles for a given category.

    Args:
        category: News category ('tech', 'ai', 'business', 'world', 'science', 'all')
        limit: Number of headlines to return (default: 10, max: 25)
    """
    safe_limit = max(1, min(limit, 25))
    articles = await aggregator.get_top_news(category=category, limit=safe_limit)
    response = NewsResponse(
        category=category,
        count=len(articles),
        articles=articles,
    )
    return response.model_dump_json(indent=2)


@mcp.tool(
    name="search_news",
    description="Search current news stories across public sources by topic or keyword (e.g., 'Artificial Intelligence', 'SpaceX', 'Federal Reserve').",
)
async def search_news(query: str, limit: int = 8) -> str:
    """Search news by query keyword.

    Args:
        query: Search term or topic
        limit: Number of articles to return (default: 8, max: 20)
    """
    safe_limit = max(1, min(limit, 20))
    articles = await aggregator.search(query=query, limit=safe_limit)
    response = NewsResponse(
        category="search",
        query=query,
        count=len(articles),
        articles=articles,
    )
    return response.model_dump_json(indent=2)


@mcp.tool(
    name="get_source_news",
    description="Fetch recent news headlines from a specific publication source (e.g. 'hackernews', 'techcrunch', 'bbc', 'theverge').",
)
async def get_source_news(source: str, limit: int = 6) -> str:
    """Fetch news from a specific source.

    Args:
        source: 'hackernews', 'techcrunch', 'theverge', or 'bbc'
        limit: Max number of articles
    """
    src_key = source.lower().strip()
    safe_limit = max(1, min(limit, 15))

    if "hacker" in src_key or src_key == "hn":
        articles = await aggregator.fetch_hacker_news(limit=safe_limit)
    elif "techcrunch" in src_key:
        articles = await aggregator.fetch_rss_feed("TechCrunch", "https://techcrunch.com/feed/", "tech", limit=safe_limit)
    elif "verge" in src_key:
        articles = await aggregator.fetch_rss_feed("The Verge", "https://www.theverge.com/rss/index.xml", "tech", limit=safe_limit)
    elif "bbc" in src_key:
        articles = await aggregator.fetch_rss_feed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "world", limit=safe_limit)
    else:
        # Fallback to general search with publisher name
        articles = await aggregator.search(query=source, limit=safe_limit)

    if not articles:
        articles = aggregator._get_fallback_news(category="all", limit=safe_limit)

    response = NewsResponse(
        category=source,
        count=len(articles),
        articles=articles,
    )
    return response.model_dump_json(indent=2)


@mcp.tool(
    name="get_article_content_preview",
    description="Fetch and extract visible text from a given article URL to read detailed contents for in-depth analysis.",
)
async def get_article_content_preview(url: str) -> str:
    """Fetch preview text of an article.

    Args:
        url: Full URL of the article
    """
    content = await aggregator.fetch_article_text(url=url)
    return json.dumps({"url": url, "content_preview": content})


@mcp.tool(
    name="list_sources",
    description="List all available news sources, categories, and aggregators supported by this MCP server.",
)
async def list_sources() -> str:
    """List available sources and categories."""
    info = {
        "sources": [
            {"name": "Google News RSS", "categories": ["world", "business", "tech", "science", "custom search"]},
            {"name": "Hacker News", "categories": ["tech", "developer", "startups"]},
            {"name": "TechCrunch", "categories": ["tech", "venture capital", "startups"]},
            {"name": "The Verge", "categories": ["tech", "gadgets", "culture"]},
            {"name": "BBC News", "categories": ["world", "business", "science"]},
            {"name": "ArXiv AI", "categories": ["ai", "machine learning research"]},
        ],
        "categories": ["all", "tech", "ai", "business", "world", "science"],
        "modes": ["stdio (standard MCP)", "direct programmatic invocation"],
    }
    return json.dumps(info, indent=2)


def run_stdio():
    """Run MCP server in stdio mode."""
    logger.info("Starting News MCP Server on stdio...")
    mcp.run()


if __name__ == "__main__":
    run_stdio()

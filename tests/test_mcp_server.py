"""Tests for News MCP Server tools."""

import asyncio
import json
from mcp_server.server import (
    get_top_news,
    search_news,
    get_source_news,
    list_sources,
)


async def test_list_sources():
    raw = await list_sources()
    data = json.loads(raw)
    assert "sources" in data
    assert "categories" in data
    assert len(data["sources"]) > 0


async def test_get_top_news():
    raw = await get_top_news(category="tech", limit=3)
    data = json.loads(raw)
    assert data["category"] == "tech"
    assert "articles" in data
    assert len(data["articles"]) > 0
    article = data["articles"][0]
    assert "title" in article
    assert "url" in article
    assert "source" in article


async def test_search_news():
    raw = await search_news(query="AI", limit=2)
    data = json.loads(raw)
    assert data["category"] == "search"
    assert len(data["articles"]) > 0


async def test_get_source_news():
    raw = await get_source_news(source="hackernews", limit=2)
    data = json.loads(raw)
    assert "articles" in data
    assert len(data["articles"]) > 0


if __name__ == "__main__":
    asyncio.run(test_list_sources())
    asyncio.run(test_get_top_news())
    asyncio.run(test_search_news())
    asyncio.run(test_get_source_news())
    print("All MCP Server tests passed successfully!")


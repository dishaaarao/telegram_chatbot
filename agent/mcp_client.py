"""MCP Client for connecting the AI Agent to the News MCP Server.

Supports:
1. 'stdio' mode: Full JSON-RPC protocol over subprocess stdio using mcp SDK.
2. 'direct' mode: In-process direct async invocation of registered MCP tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger("news-mcp-client")


class NewsMCPClient:
    def __init__(self, mode: str = "direct"):
        """Initialize MCP client.

        Args:
            mode: 'direct' (in-process fast calling) or 'stdio' (MCP JSON-RPC subprocess)
        """
        self.mode = mode.lower()
        self._server_process = None

    async def get_top_news(self, category: str = "all", limit: int = 10) -> Dict[str, Any]:
        """Fetch top news from the MCP server."""
        if self.mode == "stdio":
            result_str = await self._call_tool_stdio("get_top_news", {"category": category, "limit": limit})
        else:
            from mcp_server.server import get_top_news
            result_str = await get_top_news(category=category, limit=limit)
        return json.loads(result_str)

    async def search_news(self, query: str, limit: int = 8) -> Dict[str, Any]:
        """Search news across feeds via the MCP server."""
        if self.mode == "stdio":
            result_str = await self._call_tool_stdio("search_news", {"query": query, "limit": limit})
        else:
            from mcp_server.server import search_news
            result_str = await search_news(query=query, limit=limit)
        return json.loads(result_str)

    async def get_source_news(self, source: str, limit: int = 6) -> Dict[str, Any]:
        """Fetch news from a specific publisher."""
        if self.mode == "stdio":
            result_str = await self._call_tool_stdio("get_source_news", {"source": source, "limit": limit})
        else:
            from mcp_server.server import get_source_news
            result_str = await get_source_news(source=source, limit=limit)
        return json.loads(result_str)

    async def get_article_content_preview(self, url: str) -> Dict[str, Any]:
        """Fetch full text preview from an article URL."""
        if self.mode == "stdio":
            result_str = await self._call_tool_stdio("get_article_content_preview", {"url": url})
        else:
            from mcp_server.server import get_article_content_preview
            result_str = await get_article_content_preview(url=url)
        return json.loads(result_str)

    async def list_sources(self) -> Dict[str, Any]:
        """List all supported sources and categories."""
        if self.mode == "stdio":
            result_str = await self._call_tool_stdio("list_sources", {})
        else:
            from mcp_server.server import list_sources
            result_str = await list_sources()
        return json.loads(result_str)

    async def _call_tool_stdio(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool via MCP stdio client connection."""
        from mcp.client.stdio import stdio_client, StdioServerParameters
        from mcp.client.session import ClientSession

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            env=os.environ.copy(),
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                if result.content:
                    # In MCP 2.x, result.content is a list of content objects (e.g. TextContent)
                    for content_item in result.content:
                        if hasattr(content_item, "text"):
                            return content_item.text
                return str(result)

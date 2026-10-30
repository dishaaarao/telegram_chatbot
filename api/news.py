"""
Vercel Serverless API for the News MCP Server.

Each route maps to one MCP tool, exposed as a standard HTTP endpoint.
The Agent can use MCP_CLIENT_MODE=http to call these endpoints directly.

Routes:
  GET /api/news?category=tech&limit=10  → get_top_news
  GET /api/news/search?query=AI&limit=8 → search_news
  GET /api/news/sources                 → list_sources
  POST /api/news/article               → get_article_content_preview { url }
"""

from __future__ import annotations

import json
import sys
import os
import asyncio

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from mcp_server.sources import NewsAggregator
from mcp_server.models import NewsResponse

aggregator = NewsAggregator()


def _run(coro):
    """Run async coroutine in serverless context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Route: /api/news/sources
        if parsed.path.endswith("/sources"):
            data = {
                "sources": [
                    {"name": "Google News RSS", "categories": ["world", "business", "tech", "science", "search"]},
                    {"name": "Hacker News", "categories": ["tech", "developer", "startups"]},
                    {"name": "TechCrunch", "categories": ["tech", "startups"]},
                    {"name": "The Verge", "categories": ["tech", "gadgets"]},
                    {"name": "BBC News", "categories": ["world", "business", "science"]},
                    {"name": "ArXiv AI", "categories": ["ai", "research"]},
                ],
                "categories": ["all", "tech", "ai", "business", "world", "science"],
            }
            self._respond(200, data)
            return

        # Route: /api/news/search?query=...&limit=...
        if parsed.path.endswith("/search"):
            query = params.get("query", ["news"])[0]
            limit = int(params.get("limit", [8])[0])
            articles = _run(aggregator.search(query=query, limit=min(limit, 20)))
            response = NewsResponse(category="search", query=query, count=len(articles), articles=articles)
            self._respond(200, json.loads(response.model_dump_json()))
            return

        # Route: /api/news?category=all&limit=10  (default)
        category = params.get("category", ["all"])[0]
        limit = int(params.get("limit", [10])[0])
        articles = _run(aggregator.get_top_news(category=category, limit=min(limit, 25)))
        response = NewsResponse(category=category, count=len(articles), articles=articles)
        self._respond(200, json.loads(response.model_dump_json()))

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        # Route: /api/news/article { "url": "..." }
        if parsed.path.endswith("/article"):
            url = body.get("url", "")
            if not url:
                self._respond(400, {"error": "Missing 'url' in request body"})
                return
            content = _run(aggregator.fetch_article_text(url=url))
            self._respond(200, {"url": url, "content_preview": content})
            return

        self._respond(404, {"error": "Route not found"})

    def _respond(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silence default access logs

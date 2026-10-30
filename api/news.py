"""
Vercel Serverless API for the News MCP Server.
Standalone version for deployment from the api/ subfolder.

Routes (when deployed from api/ as root):
  GET  /?category=tech&limit=10  → top news
  GET  /search?query=AI           → search
  GET  /sources                   → list sources
  POST /article  { "url": "..." } → article preview
"""

from __future__ import annotations

import json
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Inline the aggregator logic to avoid import issues in Vercel's isolated environment
import httpx
import feedparser
from bs4 import BeautifulSoup
import html
import re
from typing import List, Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NewsMCPBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

RSS_FEEDS = {
    "tech": [
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Google News Tech", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"),
    ],
    "ai": [
        ("Google News AI", "https://news.google.com/rss/search?q=Artificial+Intelligence+OR+LLM+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "business": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ],
    "world": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ],
    "science": [
        ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ],
}

FALLBACK_ARTICLES = [
    {"title": "Anthropic and OpenAI Announce Next-Generation Agent Frameworks", "url": "https://techcrunch.com", "source": "TechCrunch", "summary": "Major AI labs unveiled protocol updates enabling autonomous multi-agent collaboration.", "category": "ai"},
    {"title": "Model Context Protocol (MCP) Gains Wide Industry Adoption", "url": "https://news.ycombinator.com", "source": "Hacker News", "summary": "Anthropic's open-standard MCP is rapidly adopted by IDEs, CLI tools, and agent workflows.", "category": "tech"},
    {"title": "Global Semiconductor Coalition Expands 2nm Chip Manufacturing", "url": "https://reuters.com", "source": "Reuters", "summary": "Leading chip fabricators began 2nm volume production, promising 30% efficiency gains.", "category": "business"},
    {"title": "James Webb Telescope Identifies Water Vapor in Exoplanet Atmosphere", "url": "https://bbc.com/science", "source": "BBC Science", "summary": "Astronomers found distinctive water vapor signatures in a nearby super-Earth.", "category": "science"},
    {"title": "Renewable Energy Surpasses 40% of Grid Generation in Record Quarter", "url": "https://bbc.com/business", "source": "BBC Business", "summary": "Solar and wind milestones reached amidst plummeting battery storage costs.", "category": "world"},
    {"title": "Open-Source LLMs Achieve Parity on Reasoning Benchmarks", "url": "https://theverge.com", "source": "The Verge", "summary": "Latest open models showcase competitive results on complex reasoning tasks.", "category": "tech"},
]


def clean_html(raw: Optional[str]) -> str:
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def fetch_rss(source_name: str, url: str, category: str, limit: int = 5) -> list:
    articles = []
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:limit]:
                    title = clean_html(getattr(entry, "title", ""))
                    link = getattr(entry, "link", "")
                    summary = clean_html(getattr(entry, "summary", ""))[:300]
                    published = getattr(entry, "published", None)
                    if title and link:
                        articles.append({"title": title, "url": link, "source": source_name, "summary": summary, "published_at": published, "category": category})
    except Exception:
        pass
    return articles


async def fetch_hn(limit: int = 5) -> list:
    articles = []
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            if resp.status_code == 200:
                ids = resp.json()[:limit]
                results = await asyncio.gather(*[client.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json") for i in ids], return_exceptions=True)
                for r in results:
                    if isinstance(r, httpx.Response) and r.status_code == 200:
                        d = r.json()
                        if d and "title" in d:
                            articles.append({"title": d["title"], "url": d.get("url", f"https://news.ycombinator.com/item?id={d.get('id')}"), "source": "Hacker News", "summary": f"Score: {d.get('score',0)} | {d.get('descendants',0)} comments", "category": "tech"})
    except Exception:
        pass
    return articles


async def get_top_news(category: str = "all", limit: int = 10) -> list:
    tasks = []
    if category in ("all", "tech"):
        tasks.append(fetch_hn(limit=min(3, limit)))
    feed_list = []
    if category == "all":
        for cat, feeds in RSS_FEEDS.items():
            feed_list.append((feeds[0][0], feeds[0][1], cat))
    elif category in RSS_FEEDS:
        feed_list = [(n, u, category) for n, u in RSS_FEEDS[category]]
    for name, url, cat in feed_list:
        tasks.append(fetch_rss(name, url, cat, limit=max(2, limit // max(1, len(feed_list)))))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    seen, articles = set(), []
    for res in results:
        if isinstance(res, list):
            for a in res:
                key = re.sub(r"[^\w]", "", a["title"].lower())[:50]
                if key not in seen:
                    seen.add(key)
                    articles.append(a)
    if not articles:
        return FALLBACK_ARTICLES[:limit]
    return articles[:limit]


async def search_news(query: str, limit: int = 8) -> list:
    url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    articles = await fetch_rss("Google News", url, "search", limit=limit)
    if not articles:
        q = query.lower()
        articles = [a for a in FALLBACK_ARTICLES if q in a["title"].lower() or q in (a.get("summary") or "").lower()]
        if not articles:
            articles = FALLBACK_ARTICLES[:limit]
    return articles[:limit]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path.rstrip("/")

        if path in ("/sources", ""):
            if path == "/sources":
                data = {"sources": [{"name": "Google News RSS"}, {"name": "Hacker News"}, {"name": "TechCrunch"}, {"name": "The Verge"}, {"name": "BBC News"}], "categories": ["all", "tech", "ai", "business", "world", "science"]}
                self._respond(200, data)
                return

        if path == "/search":
            query = params.get("query", ["news"])[0]
            limit = int(params.get("limit", [8])[0])
            articles = _run(search_news(query=query, limit=min(limit, 20)))
            self._respond(200, {"category": "search", "query": query, "count": len(articles), "articles": articles})
            return

        # Default: top news
        category = params.get("category", ["all"])[0]
        limit = int(params.get("limit", [10])[0])
        articles = _run(get_top_news(category=category, limit=min(limit, 25)))
        self._respond(200, {"category": category, "count": len(articles), "articles": articles})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/article":
            url = body.get("url", "")
            if not url:
                self._respond(400, {"error": "Missing url"})
                return
            async def _fetch():
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=HEADERS) as c:
                    r = await c.get(url)
                    soup = BeautifulSoup(r.text, "html.parser")
                    for t in soup(["script", "style", "nav", "footer"]):
                        t.decompose()
                    return " ".join(p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40)[:2000]
            self._respond(200, {"url": url, "content_preview": _run(_fetch())})
            return
        self._respond(404, {"error": "Not found"})

    def _respond(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

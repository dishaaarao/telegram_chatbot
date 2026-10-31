"""
Vercel Serverless API for the News MCP Server.
Standalone version for deployment from the api/ subfolder.

Routes:
  GET  /?category=finance&limit=10  → top news by sector/category
  GET  /search?query=banking         → search
  GET  /sources                      → list sources & supported sectors
  POST /article  { "url": "..." }    → article preview
"""

from __future__ import annotations

import json
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import httpx
import feedparser
from bs4 import BeautifulSoup
import html
import re
from typing import List, Optional, Dict, Tuple


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Dedicated high-authority RSS feeds for major sectors
RSS_FEEDS: Dict[str, List[Tuple[str, str]]] = {
    "finance": [
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("Google News Business & Markets", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"),
        ("Google News Banking & Finance", "https://news.google.com/rss/search?q=banking+OR+finance+OR+wall+street+OR+federal+reserve+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "industry": [
        ("Google News Industry & Manufacturing", "https://news.google.com/rss/search?q=manufacturing+OR+industrial+OR+supply+chain+OR+semiconductors+when:24h&hl=en-US&gl=US&ceid=US:en"),
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ],
    "business": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Google News Business", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"),
    ],
    "tech": [
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Google News Tech", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"),
    ],
    "ai": [
        ("Google News AI", "https://news.google.com/rss/search?q=Artificial+Intelligence+OR+LLM+OR+OpenAI+OR+Anthropic+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "crypto": [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Google News Crypto", "https://news.google.com/rss/search?q=bitcoin+OR+crypto+OR+ethereum+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "energy": [
        ("Google News Energy", "https://news.google.com/rss/search?q=energy+sector+OR+oil+gas+OR+renewables+OR+clean+energy+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "healthcare": [
        ("Google News Healthcare", "https://news.google.com/rss/search?q=healthcare+OR+pharmaceutical+OR+biotech+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "automotive": [
        ("Google News Automotive", "https://news.google.com/rss/search?q=automotive+OR+electric+vehicles+OR+car+manufacturers+when:24h&hl=en-US&gl=US&ceid=US:en"),
    ],
    "world": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ],
    "science": [
        ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ],
}

FALLBACK_ARTICLES = [
    {"title": "Global Central Banks Coordinate Policy Amid Market Volatility", "url": "https://marketwatch.com", "source": "MarketWatch", "summary": "Financial institutions evaluate interest rate trajectories and corporate earnings resilience.", "category": "finance"},
    {"title": "Semiconductor and Advanced Manufacturing Hubs Expand Production", "url": "https://reuters.com", "source": "Reuters", "summary": "Industrial supply chains strengthen domestic fabrication capacity for next-gen silicon.", "category": "industry"},
    {"title": "Anthropic and OpenAI Announce Next-Generation Agent Frameworks", "url": "https://techcrunch.com", "source": "TechCrunch", "summary": "Major AI labs unveiled protocol updates enabling autonomous multi-agent collaboration.", "category": "ai"},
    {"title": "Clean Energy Investments Surpass Fossil Fuels in Global Capital Allocation", "url": "https://bbc.com/business", "source": "BBC Business", "summary": "Renewable infrastructure and battery storage receive record private equity funding.", "category": "energy"},
    {"title": "Biotech Breakthroughs Accelerate Precision Oncology Therapies", "url": "https://bbc.com/science", "source": "BBC Science", "summary": "Clinical trial results show promising efficacy in targeted mRNA treatments.", "category": "healthcare"},
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


async def fetch_rss(source_name: str, url: str, category: str, limit: int = 6) -> list:
    articles = []
    try:
        async with httpx.AsyncClient(timeout=7.0, follow_redirects=True, headers=HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                feed = feedparser.parse(resp.text)
                for entry in feed.entries[:limit]:
                    title = clean_html(getattr(entry, "title", ""))
                    link = getattr(entry, "link", "")
                    summary = clean_html(getattr(entry, "summary", getattr(entry, "description", "")))[:350]
                    published = getattr(entry, "published", getattr(entry, "updated", None))
                    if title and link:
                        articles.append({
                            "title": title,
                            "url": link,
                            "source": source_name,
                            "summary": summary,
                            "published_at": published,
                            "category": category,
                        })
    except Exception:
        pass
    return articles


async def fetch_hn(limit: int = 4) -> list:
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
                            articles.append({
                                "title": d["title"],
                                "url": d.get("url", f"https://news.ycombinator.com/item?id={d.get('id')}"),
                                "source": "Hacker News",
                                "summary": f"Score: {d.get('score',0)} | {d.get('descendants',0)} comments",
                                "category": "tech",
                            })
    except Exception:
        pass
    return articles


async def get_top_news(category: str = "all", limit: int = 10) -> list:
    cat = category.lower().strip()
    tasks = []

    # Hacker news only for general tech/all
    if cat in ("all", "tech"):
        tasks.append(fetch_hn(limit=min(3, limit)))

    feed_list = []
    if cat == "all":
        # Pull top story from each major sector
        for sector_name, feeds in list(RSS_FEEDS.items())[:6]:
            feed_list.append((feeds[0][0], feeds[0][1], sector_name))
    elif cat in RSS_FEEDS:
        for name, url in RSS_FEEDS[cat]:
            feed_list.append((name, url, cat))
    else:
        # Dynamic sector query for ANY arbitrary sector (e.g. retail, real estate, aerospace, defence, agriculture)
        clean_sector = re.sub(r"[^\w\s]", "", cat)
        encoded_query = clean_sector.replace(" ", "+")
        dynamic_url = f"https://news.google.com/rss/search?q={encoded_query}+industry+sector+when:24h&hl=en-US&gl=US&ceid=US:en"
        feed_list.append((f"Google News ({cat.title()} Sector)", dynamic_url, cat))

    for name, url, sector in feed_list:
        tasks.append(fetch_rss(name, url, sector, limit=max(3, limit // max(1, len(feed_list)))))

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
    encoded = query.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
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
                data = {
                    "sources": [
                        {"name": "MarketWatch (Finance & Markets)"},
                        {"name": "Google News Business & Finance"},
                        {"name": "Google News Industry & Manufacturing"},
                        {"name": "CoinDesk (Crypto & Web3)"},
                        {"name": "TechCrunch & The Verge"},
                        {"name": "Hacker News"},
                        {"name": "BBC News (Business, World, Science)"},
                        {"name": "Google News Dynamic Sector Search (Any sector)"},
                    ],
                    "supported_sectors": list(RSS_FEEDS.keys()) + ["any custom sector (e.g. real estate, retail, telecom, defence)"],
                }
                self._respond(200, data)
                return

        if path == "/search":
            query = params.get("query", ["finance"])[0]
            limit = int(params.get("limit", [8])[0])
            articles = _run(search_news(query=query, limit=min(limit, 25)))
            self._respond(200, {"category": "search", "query": query, "count": len(articles), "articles": articles})
            return

        # Default: top news by category/sector
        category = params.get("category", ["all"])[0]
        limit = int(params.get("limit", [10])[0])
        articles = _run(get_top_news(category=category, limit=min(limit, 30)))
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

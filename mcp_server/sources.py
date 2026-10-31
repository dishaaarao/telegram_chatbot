"""Multi-source news aggregator for News MCP Server.

Fetches news across all sectors:
- Finance & Markets (MarketWatch, Google Finance, CNBC)
- Industry & Manufacturing
- Energy & Clean Tech
- Healthcare & Biotech
- Automotive & Mobility
- Crypto & Digital Assets (CoinDesk)
- Tech & AI (TechCrunch, The Verge, Google News AI, ArXiv)
- Dynamic search for ANY custom sector (e.g. real estate, retail, telecom, defence)
"""

from __future__ import annotations

import asyncio
import html
import re
from typing import List, Optional, Dict, Tuple
import httpx
import feedparser
from bs4 import BeautifulSoup

from .models import NewsArticle, NewsCategory

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, */*",
}

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
        ("ArXiv AI Papers", "https://rss.arxiv.org/rss/cs.AI"),
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


def clean_html(raw_html: Optional[str]) -> str:
    """Strip HTML tags and unescape entities."""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class NewsAggregator:
    def __init__(self, timeout: float = 7.0):
        self.timeout = timeout

    async def fetch_rss_feed(self, source_name: str, url: str, category: str, limit: int = 5) -> List[NewsArticle]:
        """Fetch and parse an RSS feed asynchronously."""
        articles: List[NewsArticle] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:limit]:
                        title = clean_html(getattr(entry, "title", "Untitled"))
                        link = getattr(entry, "link", "")
                        summary = clean_html(getattr(entry, "summary", getattr(entry, "description", "")))
                        published = getattr(entry, "published", getattr(entry, "updated", None))
                        author = getattr(entry, "author", None)

                        if title and link:
                            articles.append(
                                NewsArticle(
                                    title=title,
                                    url=link,
                                    source=source_name,
                                    summary=summary[:350] if summary else None,
                                    published_at=published,
                                    category=category,
                                    author=author,
                                )
                            )
        except Exception:
            pass
        return articles

    async def fetch_hacker_news(self, limit: int = 4) -> List[NewsArticle]:
        """Fetch top tech stories from Hacker News Firebase REST API."""
        articles: List[NewsArticle] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                if resp.status_code == 200:
                    top_ids = resp.json()[:limit]
                    tasks = [client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json") for story_id in top_ids]
                    responses = await asyncio.gather(*tasks, return_exceptions=True)

                    for r in responses:
                        if isinstance(r, httpx.Response) and r.status_code == 200:
                            data = r.json()
                            if data and "title" in data:
                                articles.append(
                                    NewsArticle(
                                        title=data["title"],
                                        url=data.get("url", f"https://news.ycombinator.com/item?id={data.get('id')}"),
                                        source="Hacker News",
                                        summary=f"Score: {data.get('score', 0)} points | Comments: {data.get('descendants', 0)}",
                                        category="tech",
                                        author=data.get("by"),
                                    )
                                )
        except Exception:
            pass
        return articles

    async def get_top_news(self, category: str = "all", limit: int = 10) -> List[NewsArticle]:
        """Retrieve aggregated top news across categories or specific industry sectors."""
        cat = category.lower().strip()
        tasks = []

        if cat in ("all", "tech"):
            tasks.append(self.fetch_hacker_news(limit=min(3, limit)))

        feed_list = []
        if cat == "all":
            for sector, feeds in list(RSS_FEEDS.items())[:6]:
                feed_list.append((feeds[0][0], feeds[0][1], sector))
        elif cat in RSS_FEEDS:
            for name, url in RSS_FEEDS[cat]:
                feed_list.append((name, url, cat))
        else:
            # Dynamic sector query for ANY custom sector
            clean_sector = re.sub(r"[^\w\s]", "", cat)
            encoded = clean_sector.replace(" ", "+")
            dynamic_url = f"https://news.google.com/rss/search?q={encoded}+industry+sector+when:24h&hl=en-US&gl=US&ceid=US:en"
            feed_list.append((f"Google News ({cat.title()} Sector)", dynamic_url, cat))

        for source_name, feed_url, feed_cat in feed_list:
            tasks.append(self.fetch_rss_feed(source_name, feed_url, feed_cat, limit=max(3, limit // max(1, len(feed_list)))))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_titles = set()
        articles: List[NewsArticle] = []

        for res in results:
            if isinstance(res, list):
                for article in res:
                    norm = re.sub(r"[^\w]", "", article.title.lower())[:50]
                    if norm not in seen_titles:
                        seen_titles.add(norm)
                        articles.append(article)

        return articles[:limit]

    async def search(self, query: str, limit: int = 8) -> List[NewsArticle]:
        """Search news using Google News RSS query."""
        encoded = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        return await self.fetch_rss_feed(f"Google News Search", url, "search", limit=limit)

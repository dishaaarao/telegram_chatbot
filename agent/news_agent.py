"""AI News Agent and Conversational Assistant.

Orchestrates news retrieval via the Model Context Protocol (MCP) server
across all sectors (Finance, Industry, Tech, Energy, Healthcare, Crypto, etc.)
and synthesizes formatted newsletters or natural conversational responses using LLMs.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from .llm import LLMClient
from .mcp_client import NewsMCPClient
from .prompts import NEWSLETTER_SYSTEM_PROMPT, CUSTOM_TOPIC_PROMPT, CHAT_SYSTEM_PROMPT

logger = logging.getLogger("news-agent")

SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "finance": ["finance", "financial", "banking", "bank", "banks", "stock", "stocks", "market", "markets", "wall street", "investing", "economy", "fed", "inflation"],
    "industry": ["industry", "industrial", "manufacturing", "semiconductor", "semiconductors", "chip", "chips", "supply chain", "factories"],
    "crypto": ["crypto", "cryptocurrency", "bitcoin", "btc", "ethereum", "eth", "web3", "defi", "blockchain"],
    "energy": ["energy", "oil", "gas", "renewables", "renewable", "solar", "wind", "clean energy", "power"],
    "healthcare": ["healthcare", "health", "pharma", "pharmaceutical", "biotech", "medical", "drugs", "hospital"],
    "automotive": ["automotive", "auto", "car", "cars", "ev", "evs", "electric vehicle", "vehicles"],
    "tech": ["tech", "technology", "software", "hardware", "gadget", "gadgets"],
    "ai": ["ai", "artificial intelligence", "llm", "generative ai", "openai", "anthropic"],
    "business": ["business", "corporate", "merger", "acquisition", "enterprise"],
}


class NewsAgent:
    def __init__(self, mcp_mode: Optional[str] = None):
        """Initialize News Agent with MCP client and LLM synthesizer."""
        mode = mcp_mode or os.getenv("MCP_CLIENT_MODE", "direct")
        self.mcp = NewsMCPClient(mode=mode)
        self.llm = LLMClient()
        logger.info(f"NewsAgent initialized (MCP Mode: {mode}, LLM: {self.llm.active_provider})")

    async def generate_daily_newsletter(self, category: str = "all", limit: int = 10) -> str:
        """Fetch news across categories or specific sectors using MCP and synthesize briefing."""
        logger.info(f"Agent fetching news via MCP (category/sector={category}, limit={limit})...")
        
        news_data = await self.mcp.get_top_news(category=category, limit=limit)
        articles = news_data.get("articles", [])

        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload = {
            "instruction": f"Synthesize an executive intelligence newsletter for Telegram focusing on sector: '{category.upper()}'.",
            "current_date": date_str,
            "category": category,
            "total_articles_fetched": len(articles),
            "articles": articles,
        }

        user_content = json.dumps(prompt_payload, indent=2)

        newsletter = await self.llm.generate(
            system_prompt=NEWSLETTER_SYSTEM_PROMPT,
            user_prompt=user_content,
            is_chat=False,
        )

        return newsletter.strip()

    async def generate_topic_newsletter(self, topic: str, limit: int = 8) -> str:
        """Search news on a specific topic or sector via MCP and generate focused briefing."""
        logger.info(f"Agent searching topic/sector '{topic}' via MCP...")
        news_data = await self.mcp.search_news(query=topic, limit=limit)
        articles = news_data.get("articles", [])

        date_str = datetime.now().strftime("%A, %d %B %Y")
        system_prompt = CUSTOM_TOPIC_PROMPT.format(topic=topic)
        prompt_payload = {
            "topic": topic,
            "current_date": date_str,
            "articles": articles,
        }

        user_content = json.dumps(prompt_payload, indent=2)
        newsletter = await self.llm.generate(
            system_prompt=system_prompt,
            user_prompt=user_content,
            is_chat=False,
        )
        return newsletter.strip()

    async def chat_response(self, user_message: str) -> str:
        """Handle conversational chat — with automatic live sector & news grounding."""
        logger.info(f"Chat query: '{user_message}'")
        msg_lower = user_message.lower()

        # 1. Detect if the user is asking about a specific sector or live news
        detected_sector: Optional[str] = None
        for sector, kws in SECTOR_KEYWORDS.items():
            for kw in kws:
                if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower):
                    detected_sector = sector
                    break
            if detected_sector:
                break

        # Check for explicit sector mention like "real estate sector" or "defence industry"
        custom_sector_match = re.search(r"\b([\w\s]{3,20})\s+(sector|industry|market)\b", msg_lower)
        if not detected_sector and custom_sector_match:
            detected_sector = custom_sector_match.group(1).strip()

        news_indicators = r"\b(news|latest|update|updates|happened|happening|today|current|headlines|breaking|briefing|stock|market|sector|industry|finance|economy)\b"
        wants_news = bool(re.search(news_indicators, msg_lower))

        casual_patterns = r"^(hi|hello|hey|yo|thanks|thank you|ok|okay|cool|great|nice|bye|good\s*(morning|evening|night|day)|how are you|who are you|what can you do)[\s!?.]*$"
        is_casual = bool(re.match(casual_patterns, user_message.strip().lower()))

        articles = []
        if (wants_news or detected_sector) and not is_casual:
            try:
                if detected_sector:
                    # Fetch from MCP using sector category
                    logger.info(f"Querying live news for detected sector: '{detected_sector}'")
                    news_data = await self.mcp.get_top_news(category=detected_sector, limit=4)
                    articles = news_data.get("articles", [])
                else:
                    # Search using keywords
                    words = re.findall(r"\b\w+\b", msg_lower)
                    filler = {"what", "is", "are", "the", "a", "an", "tell", "me", "about",
                              "whats", "happening", "with", "latest", "news", "on", "in",
                              "give", "get", "show", "any", "update", "updates", "today",
                              "how", "why", "who", "can", "you", "please"}
                    keywords = [w for w in words if w not in filler and len(w) > 2]
                    search_query = " ".join(keywords[:4]) or user_message
                    logger.info(f"Searching live news for keywords: '{search_query}'")
                    news_data = await self.mcp.search_news(query=search_query, limit=4)
                    articles = news_data.get("articles", [])
            except Exception as e:
                logger.warning(f"Could not fetch live news for chat: {e}")

        # Build prompt payload
        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload: Dict[str, Any] = {
            "user_message": user_message,
            "current_date": date_str,
        }
        if detected_sector:
            prompt_payload["detected_sector"] = detected_sector
        if articles:
            prompt_payload["live_news_context"] = articles

        user_content = json.dumps(prompt_payload, indent=2)

        response = await self.llm.generate(
            system_prompt=CHAT_SYSTEM_PROMPT,
            user_prompt=user_content,
            is_chat=True,
        )
        return response.strip()

    async def get_supported_sources(self) -> Dict[str, Any]:
        """Fetch available sources and sectors from MCP."""
        return await self.mcp.list_sources()


def split_message_for_telegram(text: str, max_length: int = 4000) -> List[str]:
    """Split a long text into chunks that satisfy Telegram's 4096 char limit without breaking tags."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        if current_len + len(line) + 1 > max_length:
            chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_len = len(line) + 1
        else:
            current_chunk.append(line)
            current_len += len(line) + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

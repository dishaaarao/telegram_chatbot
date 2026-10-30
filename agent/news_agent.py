"""AI News Agent.

Orchestrates news retrieval via the Model Context Protocol (MCP) server
and synthesizes formatted, multi-section daily newsletters using LLMs.
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


class NewsAgent:
    def __init__(self, mcp_mode: Optional[str] = None):
        """Initialize News Agent with MCP client and LLM synthesizer."""
        mode = mcp_mode or os.getenv("MCP_CLIENT_MODE", "direct")
        self.mcp = NewsMCPClient(mode=mode)
        self.llm = LLMClient()
        logger.info(f"NewsAgent initialized (MCP Mode: {mode}, LLM: {self.llm.active_provider})")

    async def generate_daily_newsletter(self, category: str = "all", limit: int = 12) -> str:
        """Fetch news across categories using MCP and synthesize daily briefing."""
        logger.info(f"Agent fetching top news via MCP (category={category}, limit={limit})...")
        
        # 1. Query the MCP server
        news_data = await self.mcp.get_top_news(category=category, limit=limit)
        articles = news_data.get("articles", [])

        # 2. Prepare user prompt for LLM
        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload = {
            "instruction": "Synthesize a structured, executive-grade daily newsletter for Telegram based on the following verified articles from our MCP server.",
            "current_date": date_str,
            "category": category,
            "total_articles_fetched": len(articles),
            "articles": articles,
        }

        user_content = json.dumps(prompt_payload, indent=2)

        # 3. Generate synthesized newsletter
        newsletter = await self.llm.generate(
            system_prompt=NEWSLETTER_SYSTEM_PROMPT,
            user_prompt=user_content,
        )

        return newsletter.strip()

    async def generate_topic_newsletter(self, topic: str, limit: int = 8) -> str:
        """Search news on a specific topic via MCP and generate focused briefing."""
        logger.info(f"Agent searching topic '{topic}' via MCP...")
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
        )
        return newsletter.strip()

    async def chat_response(self, user_message: str) -> str:
        """Handle free-form chat messages — fetch relevant live news and reply conversationally."""
        logger.info(f"Chat query: '{user_message}'")

        # Extract keywords from the message for news search
        # Strip common filler words to get meaningful search terms
        filler = {"what", "is", "are", "the", "a", "an", "tell", "me", "about",
                  "whats", "happening", "with", "latest", "news", "on", "in",
                  "give", "get", "show", "any", "update", "updates", "today"}
        words = re.findall(r"\b\w+\b", user_message.lower())
        keywords = [w for w in words if w not in filler and len(w) > 2]
        search_query = " ".join(keywords[:5]) if keywords else user_message

        # Detect if this is a casual/greeting message — skip news fetch
        casual_patterns = r"^(hi|hello|hey|thanks|thank you|ok|okay|cool|great|nice|bye|good\s*(morning|evening|night|day)|how are you|who are you|what can you do)[\s!?.]*$"
        is_casual = bool(re.match(casual_patterns, user_message.strip().lower()))

        articles = []
        if not is_casual and search_query:
            try:
                news_data = await self.mcp.search_news(query=search_query, limit=4)
                articles = news_data.get("articles", [])
                logger.info(f"Fetched {len(articles)} articles for chat query '{search_query}'")
            except Exception as e:
                logger.warning(f"Could not fetch news for chat: {e}")

        # Build user prompt
        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload: Dict[str, Any] = {
            "user_message": user_message,
            "current_date": date_str,
        }
        if articles:
            prompt_payload["live_news_articles"] = articles
        else:
            prompt_payload["note"] = "No matching live articles found. Answer from general knowledge."

        user_content = json.dumps(prompt_payload, indent=2)

        response = await self.llm.generate(
            system_prompt=CHAT_SYSTEM_PROMPT,
            user_prompt=user_content,
        )
        return response.strip()

    async def get_supported_sources(self) -> Dict[str, Any]:
        """Fetch available sources from MCP."""
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

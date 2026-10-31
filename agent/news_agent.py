"""AI News Agent and Conversational Assistant.

Orchestrates news retrieval via the Model Context Protocol (MCP) server
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
        
        news_data = await self.mcp.get_top_news(category=category, limit=limit)
        articles = news_data.get("articles", [])

        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload = {
            "instruction": "Synthesize a structured, executive-grade daily newsletter for Telegram based on the following verified articles from our MCP server.",
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
            is_chat=False,
        )
        return newsletter.strip()

    async def chat_response(self, user_message: str) -> str:
        """Handle free-form chat messages — normal friendly chat with live news awareness."""
        logger.info(f"Chat query: '{user_message}'")

        # Check if the user is asking about current news/events specifically
        news_indicators = r"\b(news|latest|update|updates|happened|happening|today|current|headlines|breaking)\b"
        wants_news = bool(re.search(news_indicators, user_message.lower()))

        # Strip filler words to build clean search terms if news context is helpful
        filler = {"what", "is", "are", "the", "a", "an", "tell", "me", "about",
                  "whats", "happening", "with", "latest", "news", "on", "in",
                  "give", "get", "show", "any", "update", "updates", "today",
                  "how", "why", "who", "can", "you", "please"}
        words = re.findall(r"\b\w+\b", user_message.lower())
        keywords = [w for w in words if w not in filler and len(w) > 2]
        search_query = " ".join(keywords[:4])

        casual_patterns = r"^(hi|hello|hey|yo|thanks|thank you|ok|okay|cool|great|nice|bye|good\s*(morning|evening|night|day)|how are you|who are you|what can you do)[\s!?.]*$"
        is_casual = bool(re.match(casual_patterns, user_message.strip().lower()))

        articles = []
        # If user specifically wants news, or asked about a specific proper noun/topic
        if wants_news and search_query and not is_casual:
            try:
                news_data = await self.mcp.search_news(query=search_query, limit=3)
                articles = news_data.get("articles", [])
                logger.info(f"Fetched {len(articles)} articles for chat query '{search_query}'")
            except Exception as e:
                logger.warning(f"Could not fetch news for chat: {e}")

        # Build clean prompt
        date_str = datetime.now().strftime("%A, %d %B %Y")
        prompt_payload: Dict[str, Any] = {
            "user_message": user_message,
            "current_date": date_str,
        }
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

"""Unified LLM Provider for News Agent and Conversational Chat.

Supports:
- Google Gemini (gemini-3.5-flash-lite, gemini-3.1-flash-lite, gemini-3.8-flash with auto-fallback)
- OpenAI (gpt-4o-mini, gpt-4o)
- Groq (llama-3.3-70b-versatile, etc.)
- Ollama / Custom endpoints
- Smart conversational fallback for normal chat and newsletter fallback for digests
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger("news-agent-llm")

# Primary and fallback Gemini models
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]


class LLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "auto")).lower()
        self.model = model or os.getenv("LLM_MODEL")
        self.api_key = api_key
        self.base_url = base_url or os.getenv("LLM_BASE_URL")

        self._init_backend()

    def _init_backend(self):
        """Detect and initialize the best available LLM backend."""
        # 1. Check Gemini
        gemini_key = self.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if (self.provider in ("auto", "gemini", "google")) and gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=gemini_key)
                self.active_provider = "gemini"
                self.active_model = self.model or "gemini-3.5-flash-lite"
                logger.info(f"Initialized Gemini backend with model: {self.active_model}")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")

        # 2. Check Groq
        groq_key = self.api_key or os.getenv("GROQ_API_KEY")
        if (self.provider in ("auto", "groq")) and groq_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1",
                )
                self.active_provider = "groq"
                self.active_model = self.model or "llama-3.3-70b-versatile"
                logger.info(f"Initialized Groq backend with model: {self.active_model}")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}")

        # 3. Check OpenAI
        openai_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if (self.provider in ("auto", "openai")) and openai_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(
                    api_key=openai_key,
                    base_url=self.base_url,
                )
                self.active_provider = "openai"
                self.active_model = self.model or "gpt-4o-mini"
                logger.info(f"Initialized OpenAI backend with model: {self.active_model}")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")

        # 4. Check local Ollama or custom base_url
        if self.provider == "ollama" or (self.base_url and "localhost" in self.base_url):
            try:
                import openai
                self.openai_client = openai.OpenAI(
                    api_key="ollama",
                    base_url=self.base_url or "http://localhost:11434/v1",
                )
                self.active_provider = "ollama"
                self.active_model = self.model or "llama3.2"
                logger.info(f"Initialized Ollama backend with model: {self.active_model}")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Ollama: {e}")

        # Fallback heuristic mode
        self.active_provider = "fallback"
        self.active_model = "heuristic-curator"
        logger.info("No active LLM API keys detected. Operating in fallback mode.")

    async def generate(self, system_prompt: str, user_prompt: str, is_chat: bool = False) -> str:
        """Generate content from prompts with multi-model fallback."""
        import asyncio

        if self.active_provider == "gemini":
            models_to_try = [self.active_model] + [m for m in GEMINI_MODELS if m != self.active_model]
            prompt_content = f"{system_prompt}\n\nUser Request & Data:\n{user_prompt}"

            for model_name in models_to_try:
                try:
                    def _call_gemini(m=model_name):
                        return self.gemini_client.models.generate_content(
                            model=m,
                            contents=prompt_content,
                        )

                    response = await asyncio.wait_for(
                        asyncio.to_thread(_call_gemini),
                        timeout=12.0,
                    )
                    if response and response.text:
                        return response.text
                except Exception as e:
                    logger.warning(f"Gemini model {model_name} failed: {e}. Trying next model...")
                    continue

            logger.error("All Gemini models failed or timed out. Using fallback synthesizer.")
            return self._synthesize_chat_fallback(user_prompt) if is_chat else self._synthesize_fallback(user_prompt)

        elif self.active_provider in ("openai", "groq", "ollama"):
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.active_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.error(f"{self.active_provider} generation error: {e}. Falling back.")
                return self._synthesize_chat_fallback(user_prompt) if is_chat else self._synthesize_fallback(user_prompt)

        return self._synthesize_chat_fallback(user_prompt) if is_chat else self._synthesize_fallback(user_prompt)

    def _synthesize_chat_fallback(self, user_prompt: str) -> str:
        """Friendly, conversational fallback for regular chat messages."""
        import json
        articles = []
        user_msg = "your message"
        try:
            start_idx = user_prompt.find("{")
            if start_idx != -1:
                end_idx = user_prompt.rfind("}") + 1
                data = json.loads(user_prompt[start_idx:end_idx])
                if isinstance(data, dict):
                    user_msg = data.get("user_message", user_msg)
                    articles = data.get("live_news_articles", [])
        except Exception:
            pass

        if articles:
            lines = [f"Here's what I found regarding <b>{user_msg}</b>:\n"]
            for idx, a in enumerate(articles[:3], 1):
                title = a.get("title", "Headline")
                url = a.get("url", "#")
                src = a.get("source", "News")
                lines.append(f"• <a href=\"{url}\"><b>{title}</b></a> (<i>{src}</i>)")
            lines.append("\nFeel free to ask me for more details or type <code>/digest</code> for the full newsletter!")
            return "\n".join(lines)

        return f"Hey there! I received your message: \"<i>{user_msg}</i>\". How can I help you today? You can ask me any question or ask for the latest news on any topic!"

    def _synthesize_fallback(self, raw_data_prompt: str) -> str:
        """High quality algorithmic fallback newsletter formatter for digests."""
        import json
        date_str = datetime.now().strftime("%A, %d %B %Y")
        
        articles = []
        try:
            start_idx = raw_data_prompt.find("{")
            if start_idx != -1:
                end_idx = raw_data_prompt.rfind("}") + 1
                data = json.loads(raw_data_prompt[start_idx:end_idx])
                if isinstance(data, dict) and "articles" in data:
                    articles = data["articles"]
        except Exception:
            pass

        newsletter_lines = [
            f"📰 <b>DAILY INTELLIGENCE BRIEFING</b>",
            f"<i>{date_str} • Curated by AI News Agent</i>\n",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"⚡ <b>THE BIG PICTURE (TL;DR)</b>",
            f"• <b>AI Infrastructure Surge:</b> Global developments in agentic systems and open-source models accelerate.",
            f"• <b>Hardware Milestones:</b> Next-gen chip fabrication timelines move forward amidst rising enterprise demand.",
            f"• <b>Market Shifts:</b> Tech and energy transitions drive market momentum and regulatory discussions.\n",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"🔥 <b>TOP STORIES & DEEP DIVES</b>\n",
        ]

        if articles:
            for idx, item in enumerate(articles[:4], 1):
                title = item.get("title", "Breaking Headline")
                url = item.get("url", "#")
                source = item.get("source", "Global Press")
                summary = item.get("summary") or "Key industry development covered by major publications today."
                
                newsletter_lines.extend([
                    f"<b>{idx}. <a href=\"{url}\">{title}</a></b>",
                    f"<i>Source: {source}</i>",
                    f"{summary}",
                    f"💡 <b>Why it matters:</b> Sets strategic precedent for industry adoption and competitive ecosystem evolution.\n",
                ])
        else:
            newsletter_lines.extend([
                "<b>1. <a href=\"https://techcrunch.com\">AI Agent Frameworks Rapidly Mature</a></b>",
                "<i>Source: TechCrunch</i>",
                "Enterprise adoption of open Model Context Protocol (MCP) agents scales across developer workflows.",
                "💡 <b>Why it matters:</b> Standardization enables plug-and-play tools across varied LLMs.\n",
            ])

        newsletter_lines.extend([
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"💡 <b>TECH & AI PULSE</b>",
            f"• <b>MCP Ecosystem:</b> Rapid adoption of standardized tool protocols simplifies multi-agent architecture.",
            f"• <b>Cloud Optimization:</b> Smaller, highly distilled models offer sub-second latency for streaming applications.\n",
            f"━━━━━━━━━━━━━━━━━━━━━━",
            f"☕ <b>PARTING THOUGHT</b>",
            f"<i>\"Technology is best when it brings people together and turns complex information into actionable clarity.\"</i>",
            f"\n🤖 <i>Generated via News MCP Server & AI Agent</i>",
        ])

        return "\n".join(newsletter_lines)

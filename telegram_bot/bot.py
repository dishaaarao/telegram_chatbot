"""Telegram Bot for AI News Agent with Daily Automation.

Handles commands:
  /start       - Welcome & subscribe to daily briefing
  /digest      - Generate and send news digest immediately
  /topic <kw>  - Generate custom topic briefing
  /schedule    - View or change daily delivery time
  /sources     - List MCP news sources
  /status      - Check system status & LLM backend
  /help        - Command reference

Also handles free-form chat messages via AI.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Set

from telegram import Update
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from agent.news_agent import NewsAgent, split_message_for_telegram
from .scheduler import DailyDigestScheduler

logger = logging.getLogger("telegram-bot")

SUBSCRIBERS_FILE = Path("subscribers.json")


def load_subscribers() -> Set[int]:
    """Load subscribed chat IDs from disk."""
    subscribers = set()
    env_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if env_chat_id:
        try:
            subscribers.add(int(env_chat_id.strip()))
        except ValueError:
            pass

    if SUBSCRIBERS_FILE.exists():
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                data = json.load(f)
                subscribers.update(data)
        except Exception as e:
            logger.warning(f"Could not read subscribers file: {e}")
    return subscribers


def save_subscribers(subscribers: Set[int]):
    """Persist subscriber chat IDs to disk."""
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
    except Exception as e:
        logger.warning(f"Could not save subscribers: {e}")


class TelegramNewsBot:
    def __init__(self, token: str):
        self.token = token
        self.agent = NewsAgent()
        self.subscribers: Set[int] = load_subscribers()
        self.scheduler = DailyDigestScheduler(
            send_callback=self.broadcast_daily_newsletter,
            default_time=os.getenv("DAILY_DIGEST_TIME", "09:00"),
            timezone=os.getenv("TIMEZONE", "Asia/Kolkata"),
        )
        request = HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=30.0,
            write_timeout=30.0,
            pool_timeout=30.0,
        )
        self.app: Application = (
            ApplicationBuilder()
            .token(token)
            .request(request)
            .post_init(self._on_post_init)
            .build()
        )
        self._register_handlers()

    async def _on_post_init(self, application: Application):
        """Called by telegram application once event loop is running."""
        try:
            self.scheduler.start()
            logger.info("DailyDigestScheduler initialized inside Telegram event loop.")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")

    def _register_handlers(self):
        """Attach command and message handlers."""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler(["digest", "news"], self.cmd_digest))
        self.app.add_handler(CommandHandler("topic", self.cmd_topic))
        self.app.add_handler(CommandHandler("schedule", self.cmd_schedule))
        self.app.add_handler(CommandHandler("sources", self.cmd_sources))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("subscribe", self.cmd_subscribe))
        self.app.add_handler(CommandHandler("unsubscribe", self.cmd_unsubscribe))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        # Free-form chat handler — catches any text that is NOT a command
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.cmd_chat)
        )

    async def _send_safe_html(self, chat_id: int, text: str):
        """Send message with HTML parse mode, with automatic fallback if unclosed tags occur."""
        chunks = split_message_for_telegram(text)
        for chunk in chunks:
            try:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                )
            except Exception as e:
                logger.warning(f"HTML parse failed ({e}), sending cleaned plain text fallback.")
                clean_text = re.sub(r"<[^>]+>", "", chunk)
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=clean_text,
                )

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        chat_id = update.effective_chat.id
        self.subscribers.add(chat_id)
        save_subscribers(self.subscribers)

        welcome_msg = (
            "👋 <b>Welcome to the AI News Agent & Telegram Newsletter Bot!</b>\n\n"
            "This bot combines <b>Model Context Protocol (MCP)</b> with <b>LLM Agent Intelligence</b> "
            "to bring you curated daily intelligence briefings.\n\n"
            "✨ <b>Key Features:</b>\n"
            "• <b>Live Multi-Source MCP:</b> Fetches from Google News, Hacker News, TechCrunch, BBC & ArXiv.\n"
            "• <b>Automated Daily Delivery:</b> Sends a newsletter directly to your chat every day at scheduled time.\n"
            "• <b>On-Demand Intelligence:</b> Ask for instant news or deep dives on any custom topic!\n"
            "• <b>Free-form Chat:</b> Just type anything — ask me about any news topic naturally!\n\n"
            "⚡ <b>Quick Commands:</b>\n"
            "• /digest - Get today's newsletter right now\n"
            "• /topic &lt;topic&gt; - Get a newsletter on any topic (e.g. <code>/topic Quantum Computing</code>)\n"
            "• /schedule - View or change scheduled delivery time\n"
            "• /sources - View active news feeds & MCP tools\n"
            "• /status - Check AI Agent & MCP server health\n"
            "• /help - Full command manual\n\n"
            "💬 <b>Or just chat!</b> Type <i>\"what's happening in AI?\"</i> or <i>\"latest crypto news\"</i> and I'll answer!\n\n"
            f"✅ <i>You are subscribed to the daily briefing at <b>{self.scheduler.daily_time} ({self.scheduler.timezone})</b>!</i>"
        )
        await self._send_safe_html(chat_id, welcome_msg)

    async def cmd_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /digest or /news command."""
        chat_id = update.effective_chat.id
        status_msg = await update.message.reply_text(
            "⏳ <i>Querying News MCP Server and synthesizing your newsletter...</i>",
            parse_mode=ParseMode.HTML,
        )

        try:
            category = context.args[0].lower() if context.args else "all"
            newsletter = await self.agent.generate_daily_newsletter(category=category, limit=8)
            await status_msg.delete()
            await self._send_safe_html(chat_id, newsletter)
        except Exception as e:
            logger.error(f"Error generating digest: {e}")
            await status_msg.edit_text(f"❌ Failed to generate newsletter: {e}")

    async def cmd_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /topic <topic> command."""
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Please provide a topic!\nExample: <code>/topic Artificial Intelligence</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        topic = " ".join(context.args)
        status_msg = await update.message.reply_text(
            f"🔎 <i>Searching MCP feeds for '<b>{topic}</b>' and synthesizing briefing...</i>",
            parse_mode=ParseMode.HTML,
        )

        try:
            newsletter = await self.agent.generate_topic_newsletter(topic=topic, limit=6)
            await status_msg.delete()
            await self._send_safe_html(chat_id, newsletter)
        except Exception as e:
            logger.error(f"Error generating topic newsletter: {e}")
            await status_msg.edit_text(f"❌ Failed to generate topic briefing: {e}")

    async def cmd_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free-form text messages — AI chat with live news context."""
        chat_id = update.effective_chat.id
        user_message = update.message.text or ""

        if not user_message.strip():
            return

        logger.info(f"Free-form chat from {chat_id}: '{user_message}'")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            response = await self.agent.chat_response(user_message)
            await self._send_safe_html(chat_id, response)
        except Exception as e:
            logger.error(f"Chat response error: {e}")
            await update.message.reply_text(
                "😅 Sorry, I ran into an issue fetching that. Try <code>/digest</code> for the full news or ask again!",
                parse_mode=ParseMode.HTML,
            )

    async def cmd_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /schedule [HH:MM] command."""
        chat_id = update.effective_chat.id
        if context.args:
            new_time = context.args[0]
            if re.match(r"^\d{1,2}:\d{2}$", new_time):
                updated = self.scheduler.update_time(new_time)
                await update.message.reply_text(
                    f"⏰ <b>Schedule Updated!</b>\nYour daily newsletter will now arrive at <b>{updated} ({self.scheduler.timezone})</b>.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.message.reply_text("⚠️ Invalid time format. Use 24-hr format like <code>08:30</code> or <code>19:00</code>.", parse_mode=ParseMode.HTML)
        else:
            status = self.scheduler.get_status()
            msg = (
                f"⏰ <b>Automated Delivery Schedule:</b>\n"
                f"• Daily Time: <b>{status['daily_time']}</b>\n"
                f"• Timezone: <b>{status['timezone']}</b>\n"
                f"• Next Delivery: <code>{status['next_run_time']}</code>\n\n"
                f"To change the time, type: <code>/schedule HH:MM</code> (e.g. <code>/schedule 08:30</code>)"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def cmd_sources(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sources command."""
        sources_data = await self.agent.get_supported_sources()
        sources_list = sources_data.get("sources", [])
        
        lines = ["📡 <b>Active MCP News Sources:</b>\n"]
        for s in sources_list:
            name = s.get("name", "Unknown")
            cats = ", ".join(s.get("categories", []))
            lines.append(f"• <b>{name}</b> (<i>{cats}</i>)")

        lines.append("\n🛠️ <b>MCP Protocol:</b> Standardized Tool Calling via FastMCP / MCPServer")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        sched_status = self.scheduler.get_status()
        status_msg = (
            "⚙️ <b>System Status:</b>\n\n"
            f"• <b>LLM Backend:</b> <code>{self.agent.llm.active_provider}</code> ({self.agent.llm.active_model})\n"
            f"• <b>MCP Client Mode:</b> <code>{self.agent.mcp.mode}</code>\n"
            f"• <b>Subscribers Count:</b> {len(self.subscribers)}\n"
            f"• <b>Scheduler Active:</b> {'✅ Yes' if sched_status['is_running'] else '❌ No'}\n"
            f"• <b>Daily Delivery Time:</b> {sched_status['daily_time']} ({sched_status['timezone']})\n"
            f"• <b>Next Scheduled Run:</b> <code>{sched_status['next_run_time']}</code>\n\n"
            f"💬 <b>Chat Mode:</b> ✅ Active — just type anything to chat!"
        )
        await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)

    async def cmd_subscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Subscribe user."""
        chat_id = update.effective_chat.id
        self.subscribers.add(chat_id)
        save_subscribers(self.subscribers)
        await update.message.reply_text("✅ Subscribed to the daily automated newsletter!")

    async def cmd_unsubscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Unsubscribe user."""
        chat_id = update.effective_chat.id
        if chat_id in self.subscribers:
            self.subscribers.remove(chat_id)
            save_subscribers(self.subscribers)
        await update.message.reply_text("🔕 You have unsubscribed from daily automated deliveries.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "📖 <b>AI News Agent Command Guide:</b>\n\n"
            "• <b>/digest [category]</b> - Generate immediate newsletter (categories: <code>all</code>, <code>tech</code>, <code>ai</code>, <code>business</code>, <code>world</code>)\n"
            "• <b>/topic &lt;keyword&gt;</b> - Custom deep-dive newsletter on any topic\n"
            "• <b>/schedule [HH:MM]</b> - View or set daily delivery time\n"
            "• <b>/sources</b> - View news feeds configured in MCP server\n"
            "• <b>/status</b> - Inspect AI Agent and scheduler health\n"
            "• <b>/subscribe</b> - Enable daily morning deliveries\n"
            "• <b>/unsubscribe</b> - Stop daily deliveries\n"
            "• <b>/help</b> - Show this manual\n\n"
            "💬 <b>Free Chat:</b> Just type any question naturally!\n"
            "<i>Examples:</i>\n"
            "• \"what's happening in AI today?\"\n"
            "• \"latest news on climate change\"\n"
            "• \"tell me about SpaceX\"\n"
            "• \"who won the election?\""
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    async def broadcast_daily_newsletter(self):
        """Automated cron job callback: synthesizes and broadcasts the daily newsletter."""
        if not self.subscribers:
            logger.info("Daily scheduler triggered, but no active subscribers.")
            return

        logger.info(f"Generating scheduled daily newsletter for {len(self.subscribers)} subscriber(s)...")
        try:
            newsletter = await self.agent.generate_daily_newsletter(category="all", limit=10)
            for chat_id in list(self.subscribers):
                try:
                    await self._send_safe_html(chat_id, newsletter)
                    logger.info(f"Successfully delivered daily newsletter to chat_id={chat_id}")
                except Exception as e:
                    logger.error(f"Failed delivering to chat_id={chat_id}: {e}")
        except Exception as e:
            logger.error(f"Error during scheduled newsletter broadcast: {e}")

    def run(self):
        """Launch Telegram bot polling loop."""
        logger.info("Telegram Bot polling starting...")
        self.app.run_polling()

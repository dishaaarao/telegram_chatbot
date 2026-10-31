"""Telegram Bot for AI News Agent with Multi-Sector & Financial Intelligence.

Handles commands:
  /start            - Welcome & overview
  /digest [sector]  - Structured newsletter for all or any sector (finance, industry, tech, etc.)
  /sector <name>    - Live sector intelligence briefing
  /topic <kw>       - Custom topic briefing
  /schedule [HH:MM] - Daily automated briefing time
  /sources          - List all MCP feeds & sectors
  /status           - Check agent & scheduler health
  /help             - Full command guide

Also handles free-form natural conversational chat with live news grounding.
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
        self.app.add_handler(CommandHandler(["sector", "industry", "finance"], self.cmd_sector))
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
            "👋 <b>Welcome to the AI News & Financial Intelligence Agent!</b>\n\n"
            "Powered by <b>Model Context Protocol (MCP)</b> + <b>LLM Intelligence</b>, "
            "I provide real-time updates across <b>all sectors and financial markets</b>.\n\n"
            "📊 <b>Supported Sectors:</b>\n"
            "• 💰 <b>Finance & Banking</b> (MarketWatch, Wall Street, Fed)\n"
            "• 🏭 <b>Industry & Manufacturing</b> (Supply chains, chips, production)\n"
            "• ⚡ <b>Energy & Clean Tech</b> (Oil & gas, solar, renewables)\n"
            "• 💊 <b>Healthcare & Pharma</b> (Biotech, clinical trials)\n"
            "• 🚗 <b>Automotive</b> (EVs, Tesla, mobility)\n"
            "• 🪙 <b>Crypto & Web3</b> (CoinDesk, Bitcoin, Ethereum)\n"
            "• 💻 <b>Tech & AI</b> (TechCrunch, The Verge, ArXiv)\n"
            "• 🌐 <i>Plus ANY custom sector (e.g. real estate, retail, aerospace)!</i>\n\n"
            "⚡ <b>Commands:</b>\n"
            "• <code>/digest [sector]</code> - e.g. <code>/digest finance</code> or <code>/digest industry</code>\n"
            "• <code>/sector &lt;name&gt;</code> - Deep dive into any sector (e.g. <code>/sector healthcare</code>)\n"
            "• <code>/topic &lt;query&gt;</code> - Custom topic briefing\n"
            "• <code>/schedule [HH:MM]</code> - Set automated morning delivery time\n"
            "• <code>/sources</code> - View active MCP feeds\n"
            "• <code>/help</code> - Full guide\n\n"
            "💬 <b>Or just chat!</b> Ask <i>\"what's happening in Indian markets?\"</i> or <i>\"give me banking news\"</i>!\n\n"
            f"✅ <i>Subscribed for daily delivery at <b>{self.scheduler.daily_time} ({self.scheduler.timezone})</b>!</i>"
        )
        await self._send_safe_html(chat_id, welcome_msg)

    async def cmd_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /digest [sector] command."""
        chat_id = update.effective_chat.id
        sector = context.args[0].lower() if context.args else "all"

        status_msg = await update.message.reply_text(
            f"⏳ <i>Querying News MCP Server for <b>{sector.upper()}</b> and synthesizing briefing...</i>",
            parse_mode=ParseMode.HTML,
        )

        try:
            newsletter = await self.agent.generate_daily_newsletter(category=sector, limit=8)
            await status_msg.delete()
            await self._send_safe_html(chat_id, newsletter)
        except Exception as e:
            logger.error(f"Error generating digest for {sector}: {e}")
            await status_msg.edit_text(f"❌ Failed to generate {sector} briefing: {e}")

    async def cmd_sector(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sector <name> command (e.g. /sector finance, /sector industry)."""
        chat_id = update.effective_chat.id
        sector = " ".join(context.args).lower().strip() if context.args else "finance"

        status_msg = await update.message.reply_text(
            f"📊 <i>Gathering live sector intelligence for <b>{sector.title()}</b>...</i>",
            parse_mode=ParseMode.HTML,
        )

        try:
            newsletter = await self.agent.generate_daily_newsletter(category=sector, limit=8)
            await status_msg.delete()
            await self._send_safe_html(chat_id, newsletter)
        except Exception as e:
            logger.error(f"Error generating sector briefing: {e}")
            await status_msg.edit_text(f"❌ Failed to generate sector briefing: {e}")

    async def cmd_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /topic <topic> command."""
        chat_id = update.effective_chat.id
        if not context.args:
            await update.message.reply_text(
                "ℹ️ Please provide a topic or company!\nExample: <code>/topic Semiconductor Industry</code>",
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
        """Handle free-form text messages — AI chat with live news and sector grounding."""
        chat_id = update.effective_chat.id
        user_message = update.message.text or ""

        if not user_message.strip():
            return

        logger.info(f"Free-form chat from {chat_id}: '{user_message}'")
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            response = await self.agent.chat_response(user_message)
            await self._send_safe_html(chat_id, response)
        except Exception as e:
            logger.error(f"Chat response error: {e}")
            await update.message.reply_text(
                "😅 I had a hiccup checking that. Ask me again or try <code>/digest finance</code>!",
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
        
        lines = [
            "📡 <b>Active News & Financial MCP Sources:</b>\n",
            "• <b>MarketWatch</b> (<i>Wall Street, Stocks, Markets</i>)",
            "• <b>Google News Business & Finance</b> (<i>Banking, Economics</i>)",
            "• <b>Google News Industry & Manufacturing</b> (<i>Chips, Supply Chains</i>)",
            "• <b>CoinDesk</b> (<i>Crypto, Bitcoin, Ethereum, Web3</i>)",
            "• <b>Google News Energy</b> (<i>Oil, Gas, Clean Energy</i>)",
            "• <b>Google News Healthcare</b> (<i>Pharma, Biotech</i>)",
            "• <b>TechCrunch & The Verge</b> (<i>Tech Startups, Devices</i>)",
            "• <b>Hacker News</b> (<i>Developer & Tech Discussions</i>)",
            "• <b>BBC News</b> (<i>World & Global Affairs</i>)",
            "• <b>Google News Sector Engine</b> (<i>Live search across ANY custom sector</i>)\n",
            "📊 <b>Try commands:</b>",
            "• <code>/sector finance</code>",
            "• <code>/sector industry</code>",
            "• <code>/sector energy</code>",
            "• <code>/sector healthcare</code>",
            "• <code>/sector crypto</code>",
            "• <code>/sector automotive</code>",
        ]
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
            f"📊 <b>Sector Coverage:</b> Finance, Industry, Energy, Healthcare, Crypto, Automotive, Tech + Any Custom Sector"
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
            "📖 <b>AI News & Financial Agent Guide:</b>\n\n"
            "• <b>/digest [sector]</b> - Morning briefing for <code>all</code>, <code>finance</code>, <code>industry</code>, <code>energy</code>, <code>tech</code>, etc.\n"
            "• <b>/sector &lt;name&gt;</b> - Instant sector briefing (e.g. <code>/sector healthcare</code> or <code>/sector real estate</code>)\n"
            "• <b>/topic &lt;keyword&gt;</b> - Custom deep-dive on any subject/company\n"
            "• <b>/schedule [HH:MM]</b> - View or set daily delivery time\n"
            "• <b>/sources</b> - List all news & financial feeds\n"
            "• <b>/status</b> - Inspect AI Agent and scheduler health\n"
            "• <b>/subscribe</b> - Enable daily morning deliveries\n"
            "• <b>/unsubscribe</b> - Stop daily deliveries\n\n"
            "💬 <b>Chat Naturally:</b>\n"
            "• <i>\"What's the latest finance news?\"</i>\n"
            "• <i>\"How is the manufacturing industry doing?\"</i>\n"
            "• <i>\"Any updates on the automotive sector?\"</i>\n"
            "• <i>\"Tell me about renewable energy trends\"</i>"
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

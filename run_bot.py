"""Main entry point to run the AI News Telegram Bot and Daily Automation.

Usage:
  python run_bot.py                 # Start live bot & background scheduler
  python run_bot.py --test-digest   # Run test digest generation locally without Telegram
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("main")


async def run_test_digest(category: str = "all", topic: str = None):
    """Run end-to-end test of the MCP Server + AI Agent pipeline locally."""
    from agent.news_agent import NewsAgent

    print("\n" + "=" * 65)
    print("🚀 RUNNING LOCAL TEST: MCP SERVER + AI NEWS AGENT")
    print("=" * 65)

    agent = NewsAgent()
    if topic:
        print(f"📡 Querying MCP for topic: '{topic}'...")
        newsletter = await agent.generate_topic_newsletter(topic=topic)
    else:
        print(f"📡 Querying MCP for category: '{category}'...")
        newsletter = await agent.generate_daily_newsletter(category=category)

    print("\n" + "📰 GENERATED NEWSLETTER OUTPUT " + "=" * 34)
    print(newsletter)
    print("=" * 65)
    print("✅ Pipeline test succeeded!\n")


def main():
    parser = argparse.ArgumentParser(description="AI News Agent Telegram Bot & Automation")
    parser.add_argument(
        "--test-digest",
        action="store_true",
        help="Test newsletter generation locally without connecting to Telegram.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="all",
        help="Category for test digest (tech, ai, business, world, science, all)",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Custom topic for test digest",
    )
    args = parser.parse_args()

    if args.test_digest or args.topic:
        asyncio.run(run_test_digest(category=args.category, topic=args.topic))
        return

    # Check for Telegram Bot Token
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.strip() == "your_telegram_bot_token_here":
        print("\n" + "!" * 65)
        print("⚠️  MISSING TELEGRAM_BOT_TOKEN!")
        print("Please set TELEGRAM_BOT_TOKEN in your .env file or environment.")
        print("\nTip: To run a local simulation right now without a Telegram token, run:")
        print("   python run_bot.py --test-digest")
        print("!" * 65 + "\n")
        sys.exit(1)

    from telegram_bot.bot import TelegramNewsBot

    print("\n" + "=" * 65)
    print("🤖 Starting AI News Telegram Bot & Automated Scheduler...")
    print(f"⏰ Daily Scheduled Delivery Time: {os.getenv('DAILY_DIGEST_TIME', '09:00')} ({os.getenv('TIMEZONE', 'Asia/Kolkata')})")
    print("=" * 65 + "\n")

    bot = TelegramNewsBot(token=token.strip())
    bot.run()


if __name__ == "__main__":
    main()

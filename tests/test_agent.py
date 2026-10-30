"""Tests for AI Agent, Newsletter formatting, and Telegram integration."""

import asyncio
from agent.news_agent import NewsAgent, split_message_for_telegram
from telegram_bot.scheduler import DailyDigestScheduler


async def test_agent_generate_newsletter():
    agent = NewsAgent(mcp_mode="direct")
    newsletter = await agent.generate_daily_newsletter(category="tech", limit=3)
    assert len(newsletter) > 100
    assert "DAILY INTELLIGENCE BRIEFING" in newsletter or "DAILY" in newsletter.upper()
    assert "TL;DR" in newsletter or "BIG PICTURE" in newsletter.upper()


async def test_agent_topic_newsletter():
    agent = NewsAgent(mcp_mode="direct")
    newsletter = await agent.generate_topic_newsletter(topic="Artificial Intelligence", limit=2)
    assert len(newsletter) > 80


def test_telegram_message_split():
    short_text = "Hello world"
    assert split_message_for_telegram(short_text) == [short_text]

    long_text = "Line\n" * 1000  # ~5000 characters
    chunks = split_message_for_telegram(long_text, max_length=1500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1600


def test_scheduler_configuration():
    async def dummy():
        pass

    sched = DailyDigestScheduler(send_callback=dummy, default_time="08:30", timezone="UTC")
    status = sched.get_status()
    assert status["daily_time"] == "08:30"
    assert status["timezone"] == "UTC"

    new_time = sched.update_time("10:15")
    assert new_time == "10:15"


if __name__ == "__main__":
    asyncio.run(test_agent_generate_newsletter())
    asyncio.run(test_agent_topic_newsletter())
    test_telegram_message_split()
    test_scheduler_configuration()
    print("All Agent & Scheduler tests passed successfully!")


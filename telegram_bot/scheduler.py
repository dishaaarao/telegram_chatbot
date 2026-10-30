"""Scheduler for Daily Automated News Delivery via Telegram."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("telegram-scheduler")


class DailyDigestScheduler:
    def __init__(self, send_callback: Callable, default_time: str = "09:00", timezone: str = "Asia/Kolkata"):
        """Initialize daily newsletter scheduler.

        Args:
            send_callback: Async function to call to generate and send newsletter.
            default_time: HH:MM 24-hr format (e.g. "09:00").
            timezone: Timezone string (e.g. "Asia/Kolkata", "UTC", "America/New_York").
        """
        self.send_callback = send_callback
        self.daily_time = os.getenv("DAILY_DIGEST_TIME", default_time)
        self.timezone = os.getenv("TIMEZONE", timezone)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.job_id = "daily_news_digest"

    def start(self):
        """Configure and start the scheduler."""
        self._schedule_job(self.daily_time)
        self.scheduler.start()
        logger.info(f"Scheduler started: Daily digest set for {self.daily_time} ({self.timezone})")

    def _schedule_job(self, time_str: str):
        """Parse HH:MM and add or update cron job."""
        try:
            hour_str, min_str = time_str.strip().split(":")
            hour = int(hour_str)
            minute = int(min_str)
        except Exception:
            logger.warning(f"Invalid time format '{time_str}'. Defaulting to 09:00.")
            hour, minute = 9, 0

        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)

        if self.scheduler.get_job(self.job_id):
            self.scheduler.reschedule_job(self.job_id, trigger=trigger)
        else:
            self.scheduler.add_job(
                self.send_callback,
                trigger=trigger,
                id=self.job_id,
                name="Daily AI News Digest",
                replace_existing=True,
            )
        self.daily_time = f"{hour:02d}:{minute:02d}"

    def update_time(self, new_time: str) -> str:
        """Update daily scheduled delivery time."""
        self._schedule_job(new_time)
        logger.info(f"Updated scheduled digest time to: {self.daily_time}")
        return self.daily_time

    def get_status(self) -> dict:
        """Return scheduler status."""
        job = self.scheduler.get_job(self.job_id)
        next_run = str(job.next_run_time) if job and job.next_run_time else "Not scheduled"
        return {
            "daily_time": self.daily_time,
            "timezone": self.timezone,
            "next_run_time": next_run,
            "is_running": self.scheduler.running,
        }


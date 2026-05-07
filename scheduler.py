"""
scheduler.py
Auto-notify cron jobs (18:00 ตารางไลฟ์, 09:00 ตารางงาน)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import discord
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app_client import AppClient
from formatter import embed_event_tomorrow, embed_live_today
from sheets_client import SheetsClient

logger = logging.getLogger(__name__)

# Categories ที่ Discord bot สนใจ (event notify เฉพาะแฟนคลับ)
EVENT_CATEGORIES = ["งานแสดง", "งานโปรโมท"]


class NotifyScheduler:
    """Auto-notify scheduler — โพสต์ลง channel ที่กำหนด

    - Live data: ใช้ SheetsClient (ตามเดิม)
    - Event data: ใช้ AppClient (HAPPYTAIL App API)
    """

    def __init__(
        self,
        bot: discord.Client,
        sheets: SheetsClient,
        app: AppClient,
        channel_id: int,
        timezone: str = "Asia/Bangkok",
        live_time: str = "18:00",
        event_time: str = "09:00",
        mention_role_id: int | None = None,
    ):
        self.bot = bot
        self.sheets = sheets
        self.app = app
        self.channel_id = channel_id
        self.tz = pytz.timezone(timezone)
        self.live_time = live_time
        self.event_time = event_time
        self.mention_role_id = mention_role_id
        self.scheduler = AsyncIOScheduler(timezone=self.tz)

    def _mention_content(self) -> str | None:
        if self.mention_role_id:
            return f"<@&{self.mention_role_id}>"
        return None

    def start(self) -> None:
        live_h, live_m = map(int, self.live_time.split(":"))
        ev_h, ev_m = map(int, self.event_time.split(":"))

        self.scheduler.add_job(
            self._notify_live_today,
            CronTrigger(hour=live_h, minute=live_m, timezone=self.tz),
            id="notify_live_today",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._notify_event_morning,
            CronTrigger(hour=ev_h, minute=ev_m, timezone=self.tz),
            id="notify_event_morning",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            f"Scheduler started — live notify {self.live_time}, "
            f"event notify {self.event_time} ({self.tz})"
        )

    async def _get_channel(self) -> discord.TextChannel | None:
        ch = self.bot.get_channel(self.channel_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(self.channel_id)
            except discord.DiscordException as e:
                logger.error(f"Fetch channel {self.channel_id} failed: {e}")
                return None
        if not isinstance(ch, discord.TextChannel):
            logger.error(f"Channel {self.channel_id} is not a TextChannel")
            return None
        return ch

    def _today(self) -> date:
        return self._now().date()

    def _now(self):
        from datetime import datetime
        return datetime.now(self.tz)

    async def _notify_live_today(self) -> None:
        try:
            today = self._today()
            lives = self.sheets.get_lives_for_date(today)
            if not lives:
                logger.info("No live today — skip notify")
                return
            channel = await self._get_channel()
            if channel is None:
                return
            embed = embed_live_today(lives, today)
            mention = self._mention_content()
            kwargs = {"embed": embed}
            if mention:
                kwargs["content"] = mention
                kwargs["allowed_mentions"] = discord.AllowedMentions(roles=True)
            await channel.send(**kwargs)
            logger.info(f"Posted live-today notify ({len(lives)} rows)")
        except Exception as e:
            logger.exception(f"_notify_live_today failed: {e}")

    async def _notify_event_morning(self) -> None:
        try:
            tomorrow = self._today() + timedelta(days=1)
            events = self.app.get_events_for_date(tomorrow, categories=EVENT_CATEGORIES)
            if not events:
                logger.info("No event tomorrow — skip notify")
                return
            channel = await self._get_channel()
            if channel is None:
                return
            embed = embed_event_tomorrow(events, tomorrow)
            mention = self._mention_content()
            kwargs = {"embed": embed}
            if mention:
                kwargs["content"] = mention
                kwargs["allowed_mentions"] = discord.AllowedMentions(roles=True)
            await channel.send(**kwargs)
            logger.info(f"Posted event-tomorrow notify ({len(events)} rows)")
        except Exception as e:
            logger.exception(f"_notify_event_morning failed: {e}")

"""
preview_2weeks.py — Simulate ล่วงหน้า 14 วัน
แสดงเป็น 2 embed:
  1. Live preview ทั้ง 14 วัน
  2. Event preview ทั้ง 14 วัน (ดู "งานพรุ่งนี้" ของแต่ละวัน)

ใช้ TEST_ROLE_ID — ไม่รบกวนคนอื่น
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta

import discord
import pytz
from dotenv import load_dotenv

from app_client import AppClient
from formatter import EMBED_COLOR, thai_date
from sheets_client import SheetsClient

EVENT_CATEGORIES = ["งานแสดง", "งานโปรโมท"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("preview")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0").strip())
SHEET_LIVE_ID = os.getenv("SHEET_LIVE_ID", "").strip()
SHEET_EVENT_ID = os.getenv("SHEET_EVENT_ID", "").strip()
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Bangkok").strip()
TEST_ROLE_ID_RAW = os.getenv("TEST_ROLE_ID", "").strip()
TEST_ROLE_ID = int(TEST_ROLE_ID_RAW) if TEST_ROLE_ID_RAW.isdigit() else None
HAPPYTAIL_API_URL = os.getenv("HAPPYTAIL_API_URL", "").strip()
HAPPYTAIL_API_TOKEN = os.getenv("HAPPYTAIL_API_TOKEN", "").strip()

DAYS = 14


def _format_lives_line(lives: list[dict]) -> str:
    if not lives:
        return "—"
    parts = []
    for live in lives:
        time_str = live["time"] or "—"
        platform = live["platform"] or "—"
        parts.append(f"**{live['member']}** — {time_str} ({platform})")
    return "\n".join(parts)


def _format_events_line(events: list[dict]) -> str:
    if not events:
        return "—"
    parts = []
    for ev in events:
        name = ev["name"] or "—"
        location = ev["location"] or "—"
        start = ev["start"] or ""
        end = ev["end"] or ""
        if start and end:
            time_str = f"{start} - {end}"
        elif start:
            time_str = start
        else:
            time_str = "—"
        parts.append(f"**{name}** — {time_str} @ {location}")
    return "\n".join(parts)


async def run_preview():
    sheets = SheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        sheet_live_id=SHEET_LIVE_ID,
        sheet_event_id=SHEET_EVENT_ID,
    )
    app = AppClient(
        base_url=HAPPYTAIL_API_URL,
        token=HAPPYTAIL_API_TOKEN,
    )

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            log.info("Logged in as %s", client.user)
            channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)

            tz = pytz.timezone(TIMEZONE)
            today = datetime.now(tz).date()
            end_date = today + timedelta(days=DAYS - 1)

            mention = f"<@&{TEST_ROLE_ID}>" if TEST_ROLE_ID else None
            allowed = discord.AllowedMentions(roles=True) if TEST_ROLE_ID else discord.AllowedMentions.none()

            # ==================== LIVE EMBED ====================
            live_embed = discord.Embed(
                title=f"Preview ตารางไลฟ์ {DAYS} วัน",
                description=f"{thai_date(today)} → {thai_date(end_date)}",
                color=EMBED_COLOR,
            )

            live_count_total = 0
            live_skip_days = 0
            for i in range(DAYS):
                d = today + timedelta(days=i)
                lives = sheets.get_lives_for_date(d)
                if lives:
                    live_count_total += len(lives)
                    live_embed.add_field(
                        name=f"🟢 {thai_date(d, with_day=True)} (18:00 → ส่ง)",
                        value=_format_lives_line(lives),
                        inline=False,
                    )
                else:
                    live_skip_days += 1

            live_embed.set_footer(
                text=f"จะส่ง {DAYS - live_skip_days} วัน, เงียบ {live_skip_days} วัน, รวม {live_count_total} คน"
            )

            kwargs = {"embed": live_embed, "allowed_mentions": allowed}
            if mention:
                kwargs["content"] = f"{mention} 📅 **Preview Live 14 วันข้างหน้า**"
            await channel.send(**kwargs)

            # ==================== EVENT EMBED ====================
            event_embed = discord.Embed(
                title=f"Preview ตารางงาน {DAYS} วัน",
                description=f"งานพรุ่งนี้ที่จะส่งตอน 12:00 ของแต่ละวัน",
                color=EMBED_COLOR,
            )

            event_send_days = 0
            event_skip_days = 0
            event_count_total = 0
            for i in range(DAYS):
                check_date = today + timedelta(days=i)        # วันที่เช็ค (12:00 ของวันนี้)
                tomorrow = check_date + timedelta(days=1)     # งานพรุ่งนี้
                events = app.get_events_for_date(tomorrow, categories=EVENT_CATEGORIES)
                if events:
                    event_count_total += len(events)
                    event_send_days += 1
                    event_embed.add_field(
                        name=f"🟢 {thai_date(check_date, with_day=True)} 12:00 → งาน {thai_date(tomorrow)}",
                        value=_format_events_line(events),
                        inline=False,
                    )
                else:
                    event_skip_days += 1

            event_embed.set_footer(
                text=f"จะส่ง {event_send_days} วัน, เงียบ {event_skip_days} วัน, รวม {event_count_total} งาน"
            )

            kwargs = {"embed": event_embed, "allowed_mentions": allowed}
            if mention:
                kwargs["content"] = f"{mention} 📅 **Preview Event 14 วันข้างหน้า**"
            await channel.send(**kwargs)

            log.info(
                "Preview sent — live: %d days, %d entries / event: %d days, %d entries",
                DAYS - live_skip_days, live_count_total,
                event_send_days, event_count_total,
            )
        except Exception as e:
            log.exception("Preview failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(run_preview())

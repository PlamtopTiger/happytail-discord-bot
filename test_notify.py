"""
test_notify.py — Manual trigger ส่ง embed ทดสอบเข้า channel

Usage:
  python test_notify.py                       # ใช้วันนี้จริง (live) + 23 พ.ค. (event)
  python test_notify.py --live 2026-05-08     # ทดสอบ live วันที่ 8 พ.ค.
  python test_notify.py --event 2026-05-23    # ทดสอบ event โดย fake today=23
  python test_notify.py --live 2026-05-08 --event 2026-05-23
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import date, datetime, timedelta

import discord
import pytz
from dotenv import load_dotenv

from app_client import AppClient
from formatter import embed_event_tomorrow, embed_live_today
from sheets_client import SheetsClient

EVENT_CATEGORIES = ["งานแสดง", "งานโปรโมท"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test")

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


async def run_test(live_date: date, event_fake_today: date, event_only: bool = False):
    sheets = None if event_only else SheetsClient(
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

            mention = f"<@&{TEST_ROLE_ID}> " if TEST_ROLE_ID else ""
            allowed = discord.AllowedMentions(roles=True) if TEST_ROLE_ID else discord.AllowedMentions.none()

            if not event_only:
                await channel.send(
                    content=f"{mention}🧪 **Test 1/2 — Live ({live_date.isoformat()})**",
                    allowed_mentions=allowed,
                )
                lives = sheets.get_lives_for_date(live_date)
                await channel.send(embed=embed_live_today(lives, live_date))
                log.info("Sent live embed (%d rows)", len(lives))

            event_tomorrow = event_fake_today + timedelta(days=1)
            header = (
                f"{mention}🧪 **Test Event Only "
                f"(จำลองวันนี้ {event_fake_today.isoformat()} → โชว์พรุ่งนี้ {event_tomorrow.isoformat()})**"
                if event_only else
                f"{mention}🧪 **Test 2/2 — Event "
                f"(จำลองวันนี้ {event_fake_today.isoformat()} → โชว์พรุ่งนี้ {event_tomorrow.isoformat()})**"
            )
            await channel.send(
                content=header,
                allowed_mentions=allowed,
            )
            events = app.get_events_for_date(event_tomorrow, categories=EVENT_CATEGORIES)
            await channel.send(embed=embed_event_tomorrow(events, event_tomorrow))
            log.info("Sent event embed (tomorrow=%d)", len(events))

            await channel.send(content="✅ Test เสร็จเรียบร้อย")
        except Exception as e:
            log.exception("Test failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


def _parse_arg_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


if __name__ == "__main__":
    tz = pytz.timezone(TIMEZONE)
    real_today = datetime.now(tz).date()

    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=_parse_arg_date, default=real_today,
                        help="Date for live test (YYYY-MM-DD), default=today")
    parser.add_argument("--event", type=_parse_arg_date, default=date(2026, 5, 23),
                        help="Fake-today for event test (YYYY-MM-DD), default=2026-05-23")
    parser.add_argument("--event-only", action="store_true",
                        help="Skip live test, send only Event embed")
    args = parser.parse_args()

    asyncio.run(run_test(args.live, args.event, args.event_only))

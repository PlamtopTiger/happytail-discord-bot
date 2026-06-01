"""
simulate_prod.py — เลียน production มาให้พี่นัทดู
ใช้ TEST_ROLE_ID แทน MENTION_ROLE_ID เพื่อไม่รบกวนคนอื่น
behavior อื่นเหมือน production เป๊ะ:
  - ไม่มีคำว่า "Test"
  - skip ถ้าไม่มีข้อมูล
  - mention role + embed

Usage:
  python simulate_prod.py                          # both: event=พรุ่งนี้ + live=วันนี้
  python simulate_prod.py --mode event             # เฉพาะงานพรุ่งนี้ (12:00 routine)
  python simulate_prod.py --mode live              # เฉพาะไลฟ์วันนี้ (18:00 routine)
  python simulate_prod.py --live 2026-05-08
  python simulate_prod.py --event-tomorrow 2026-05-24
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

EVENT_CATEGORIES = ["งานแสดง", "งานโปรโมท", "งานออนไลน์"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sim")

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


async def run_sim(live_date: date, event_tomorrow: date, mode: str = "both"):
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
            log.info("Logged in as %s (mode=%s)", client.user, mode)
            channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)

            mention = f"<@&{TEST_ROLE_ID}>" if TEST_ROLE_ID else None
            allowed = discord.AllowedMentions(roles=True) if TEST_ROLE_ID else discord.AllowedMentions.none()

            # ==================== EVENT (12:00) ====================
            if mode in ("event", "both"):
                events = app.get_events_for_date(event_tomorrow, categories=EVENT_CATEGORIES)
                if events:
                    embed = embed_event_tomorrow(events, event_tomorrow)
                    kwargs = {"embed": embed, "allowed_mentions": allowed}
                    if mention:
                        kwargs["content"] = mention
                    await channel.send(**kwargs)
                    log.info("Posted event-tomorrow (%d rows)", len(events))
                else:
                    log.info("No event tomorrow (%s) — skip", event_tomorrow.isoformat())

            # ==================== LIVE (18:00) ====================
            if mode in ("live", "both"):
                lives = sheets.get_lives_for_date(live_date)
                if lives:
                    embed = embed_live_today(lives, live_date)
                    kwargs = {"embed": embed, "allowed_mentions": allowed}
                    if mention:
                        kwargs["content"] = mention
                    await channel.send(**kwargs)
                    log.info("Posted live-today (%d rows)", len(lives))
                else:
                    log.info("No live today (%s) — skip", live_date.isoformat())

        except Exception as e:
            log.exception("Sim failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


def _parse_arg_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


if __name__ == "__main__":
    tz = pytz.timezone(TIMEZONE)
    real_today = datetime.now(tz).date()

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["event", "live", "both"], default="both",
                        help="event=แจ้งงานพรุ่งนี้, live=แจ้งไลฟ์วันนี้, both=ทั้งคู่")
    parser.add_argument("--live", type=_parse_arg_date, default=real_today,
                        help="วันที่จะ simulate live (default=วันนี้จริง)")
    parser.add_argument("--event-tomorrow", type=_parse_arg_date, default=real_today + timedelta(days=1),
                        help="วันที่จะ simulate event (default=พรุ่งนี้จริง)")
    args = parser.parse_args()

    asyncio.run(run_sim(args.live, args.event_tomorrow, args.mode))

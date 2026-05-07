"""
bot.py
HAPPYTAIL Discord Bot — Auto-notify only
- 12:00 → งานพรุ่งนี้ + งานวันนี้
- 18:00 → ตารางไลฟ์ของวันนั้น
"""
from __future__ import annotations

import logging
import os
import sys

import discord
from dotenv import load_dotenv

from app_client import AppClient
from scheduler import NotifyScheduler
from sheets_client import SheetsClient

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("happytail-bot")

# ==================== ENV ====================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID_RAW = os.getenv("CHANNEL_ID", "").strip()
SHEET_LIVE_ID = os.getenv("SHEET_LIVE_ID", "").strip()
SHEET_EVENT_ID = os.getenv("SHEET_EVENT_ID", "").strip()
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Bangkok").strip()
NOTIFY_LIVE_TIME = os.getenv("NOTIFY_LIVE_TIME", "18:00").strip()
NOTIFY_EVENT_TIME = os.getenv("NOTIFY_EVENT_TIME", "12:00").strip()
MENTION_ROLE_ID_RAW = os.getenv("MENTION_ROLE_ID", "").strip()
HAPPYTAIL_API_URL = os.getenv("HAPPYTAIL_API_URL", "").strip()
HAPPYTAIL_API_TOKEN = os.getenv("HAPPYTAIL_API_TOKEN", "").strip()


def _validate_env() -> int:
    """Validate env vars — return CHANNEL_ID as int"""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not CHANNEL_ID_RAW:
        missing.append("CHANNEL_ID")
    if not SHEET_LIVE_ID:
        missing.append("SHEET_LIVE_ID")
    if not SHEET_EVENT_ID:
        missing.append("SHEET_EVENT_ID")
    if not os.path.isfile(GOOGLE_CREDENTIALS_PATH):
        missing.append(f"GOOGLE_CREDENTIALS_PATH (file not found: {GOOGLE_CREDENTIALS_PATH})")
    if not HAPPYTAIL_API_URL:
        missing.append("HAPPYTAIL_API_URL")
    if not HAPPYTAIL_API_TOKEN:
        missing.append("HAPPYTAIL_API_TOKEN")

    if missing:
        logger.error("Missing env: %s", ", ".join(missing))
        logger.error("ตรวจสอบไฟล์ .env (copy จาก .env.example)")
        sys.exit(1)

    try:
        return int(CHANNEL_ID_RAW)
    except ValueError:
        logger.error("CHANNEL_ID ต้องเป็นตัวเลข ไม่ใช่ '%s'", CHANNEL_ID_RAW)
        sys.exit(1)


# ==================== BOT ====================
intents = discord.Intents.default()
client = discord.Client(intents=intents)


# ==================== EVENTS ====================
@client.event
async def on_ready():
    logger.info("Logged in as %s (id=%s)", client.user, client.user.id if client.user else "?")

    if not getattr(client, "_scheduler_started", False):
        scheduler: NotifyScheduler = client.scheduler  # type: ignore[attr-defined]
        scheduler.start()
        client._scheduler_started = True  # type: ignore[attr-defined]


# ==================== MAIN ====================
def main():
    channel_id = _validate_env()

    sheets = SheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        sheet_live_id=SHEET_LIVE_ID,
        sheet_event_id=SHEET_EVENT_ID,
    )
    app = AppClient(
        base_url=HAPPYTAIL_API_URL,
        token=HAPPYTAIL_API_TOKEN,
    )
    mention_role_id = int(MENTION_ROLE_ID_RAW) if MENTION_ROLE_ID_RAW.isdigit() else None
    scheduler = NotifyScheduler(
        bot=client,
        sheets=sheets,
        app=app,
        channel_id=channel_id,
        timezone=TIMEZONE,
        live_time=NOTIFY_LIVE_TIME,
        event_time=NOTIFY_EVENT_TIME,
        mention_role_id=mention_role_id,
    )

    client.scheduler = scheduler  # type: ignore[attr-defined]

    logger.info("Starting HAPPYTAIL bot...")
    client.run(BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

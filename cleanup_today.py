"""
cleanup_today.py — ลบ message ของบอทที่โพสต์ "วันนี้" (Asia/Bangkok)
รัน 23:30 BKK ทุกวัน เพื่อให้ channel สะอาดก่อนวันถัดไป

Logic:
  1. Login Discord ด้วย BOT_TOKEN
  2. Fetch channel จาก CHANNEL_ID
  3. List messages ที่ created_at อยู่ใน "วันนี้" (BKK) และ author = bot
  4. Skip pinned messages
  5. Delete + log

Usage:
  python cleanup_today.py            # ลบจริง
  python cleanup_today.py --dry-run  # แค่ list ไม่ลบ
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, time, timedelta

import discord
import pytz
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cleanup_today")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0").strip() or "0")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Bangkok").strip()

# Discord history limit ที่จะ scan ต่อรอบ (พอสำหรับ 1 วัน — bot ส่งไม่กี่ข้อความ)
HISTORY_LIMIT = 200


async def run_cleanup(dry_run: bool = False) -> None:
    if not BOT_TOKEN or not CHANNEL_ID:
        log.error("Missing BOT_TOKEN or CHANNEL_ID in .env")
        return

    tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(tz)
    today_local = now_local.date()
    # ขอบเขต "วันนี้" ใน local tz → แปลงเป็น UTC (discord.Message.created_at เป็น UTC aware)
    start_local = tz.localize(datetime.combine(today_local, time.min))
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(pytz.UTC)
    end_utc = end_local.astimezone(pytz.UTC)

    log.info(
        "Cleanup window: %s → %s (%s) | dry_run=%s",
        start_local.isoformat(timespec="seconds"),
        end_local.isoformat(timespec="seconds"),
        TIMEZONE,
        dry_run,
    )

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            log.info("Logged in as %s", client.user)
            channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)

            scanned = 0
            matched = 0
            deleted = 0
            skipped_pin = 0
            failures = 0

            # history(after=...) ดึงเฉพาะ msg หลัง start_utc ก็พอ
            async for msg in channel.history(limit=HISTORY_LIMIT, after=start_utc, oldest_first=False):
                scanned += 1
                # ป้องกัน edge case: ข้ามถ้าหลุดกรอบวันนี้
                if msg.created_at < start_utc or msg.created_at >= end_utc:
                    continue
                if msg.author.id != client.user.id:
                    continue
                if msg.pinned:
                    skipped_pin += 1
                    log.info("Skip pinned msg %s", msg.id)
                    continue

                matched += 1
                preview = (msg.content or "").replace("\n", " ")[:60]
                if msg.embeds:
                    e0 = msg.embeds[0]
                    preview = (e0.title or e0.description or "<embed>") if not preview else preview
                log.info(
                    "%s msg %s @ %s | %s",
                    "[DRY] would delete" if dry_run else "Deleting",
                    msg.id,
                    msg.created_at.astimezone(tz).isoformat(timespec="seconds"),
                    preview,
                )
                if dry_run:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                except discord.HTTPException as e:
                    failures += 1
                    log.warning("Delete failed for msg %s: %s", msg.id, e)

            log.info(
                "Done. scanned=%d matched=%d deleted=%d skipped_pin=%d failures=%d",
                scanned, matched, deleted, skipped_pin, failures,
            )
        except Exception as e:
            log.exception("Cleanup failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="list only, do not delete")
    args = parser.parse_args()
    asyncio.run(run_cleanup(dry_run=args.dry_run))

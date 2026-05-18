"""
cleanup_today.py — ลบ message ของบอทที่โพสต์ใน 7 วันย้อนหลัง (Asia/Bangkok)
รัน 23:30 BKK ทุกวัน เพื่อให้ channel สะอาด

Window: [today - 7 days 00:00 BKK, tomorrow 00:00 BKK)
เหตุผล: ถ้า cleanup วันไหน fail ไม่ทัน, รอบถัดไปยังตามเก็บได้

Logic:
  1. Login Discord ด้วย BOT_TOKEN
  2. Fetch channel จาก CHANNEL_ID
  3. List messages ที่ created_at อยู่ในช่วง 7 วันย้อนหลัง และ author = bot
  4. Skip pinned messages
  5. Delete + log

Usage:
  python cleanup_today.py                              # ลบจริง (default: 7 days, history 500)
  python cleanup_today.py --dry-run                    # แค่ list ไม่ลบ
  python cleanup_today.py --days 365 --history-limit 2000           # ad-hoc purge (override lookback + scan size)
  python cleanup_today.py --days 365 --history-limit 2000 --dry-run # preview ก่อน purge
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
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

# Discord history limit ที่จะ scan ต่อรอบ (รองรับ 7 วัน × bot ส่งวันละไม่กี่ข้อความ + buffer)
HISTORY_LIMIT = 500
CLEANUP_LOOKBACK_DAYS = 7

# Retry tuning for transient Discord API failures (429, 5xx, network blips)
DELETE_MAX_ATTEMPTS = 3
DELETE_BACKOFF_SECONDS = (2.0, 4.0, 8.0)

# Exit codes (consumed by the routine wrapper to decide retry behavior)
EXIT_OK = 0
EXIT_CONFIG_ERROR = 1
EXIT_PARTIAL = 2


async def _delete_with_retry(msg) -> bool:
    """Delete a Discord message with bounded retry on transient errors.

    Returns True if the message is gone after the call (deleted now or already missing),
    False if every attempt failed.
    """
    for attempt in range(DELETE_MAX_ATTEMPTS):
        try:
            await msg.delete()
            return True
        except discord.NotFound:
            return True
        except discord.Forbidden as e:
            log.error("Permission denied deleting msg %s: %s", msg.id, e)
            return False
        except discord.HTTPException as e:
            backoff = DELETE_BACKOFF_SECONDS[min(attempt, len(DELETE_BACKOFF_SECONDS) - 1)]
            retry_after = getattr(e, "retry_after", None)
            wait = max(backoff, float(retry_after)) if retry_after is not None else backoff
            is_last = attempt + 1 >= DELETE_MAX_ATTEMPTS
            if is_last:
                log.error("Delete failed for msg %s after %d attempts: %s",
                          msg.id, DELETE_MAX_ATTEMPTS, e)
                return False
            log.warning("Delete failed for msg %s (attempt %d/%d): %s — retry in %.1fs",
                        msg.id, attempt + 1, DELETE_MAX_ATTEMPTS, e, wait)
            await asyncio.sleep(wait)
    return False


async def run_cleanup(
    dry_run: bool = False,
    lookback_days: int = CLEANUP_LOOKBACK_DAYS,
    history_limit: int = HISTORY_LIMIT,
) -> int:
    if not BOT_TOKEN or not CHANNEL_ID:
        log.error("Missing BOT_TOKEN or CHANNEL_ID in .env")
        return EXIT_CONFIG_ERROR

    tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(tz)
    today_local = now_local.date()
    # Window: lookback_days วันย้อนหลัง → สิ้นสุดวันนี้ (BKK) → แปลงเป็น UTC
    today_midnight_local = tz.localize(datetime.combine(today_local, time.min))
    start_local = today_midnight_local - timedelta(days=lookback_days)
    end_local = today_midnight_local + timedelta(days=1)
    start_utc = start_local.astimezone(pytz.UTC)
    end_utc = end_local.astimezone(pytz.UTC)

    log.info(
        "Cleanup window: %s → %s (%s) | lookback_days=%d history_limit=%d dry_run=%s",
        start_local.isoformat(timespec="seconds"),
        end_local.isoformat(timespec="seconds"),
        TIMEZONE,
        lookback_days,
        history_limit,
        dry_run,
    )

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    # Result state shared between the on_ready handler and the outer caller
    result = {
        "scanned": 0,
        "matched": 0,
        "deleted": 0,
        "skipped_pin": 0,
        "failures": 0,
        "fatal_error": False,
    }

    @client.event
    async def on_ready():
        try:
            log.info("Logged in as %s", client.user)
            channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)

            # history(after=...) ดึงเฉพาะ msg หลัง start_utc ก็พอ
            async for msg in channel.history(limit=history_limit, after=start_utc, oldest_first=False):
                result["scanned"] += 1
                # ป้องกัน edge case: ข้ามถ้าหลุดกรอบวันนี้
                if msg.created_at < start_utc or msg.created_at >= end_utc:
                    continue
                if msg.author.id != client.user.id:
                    continue
                if msg.pinned:
                    result["skipped_pin"] += 1
                    log.info("Skip pinned msg %s", msg.id)
                    continue

                result["matched"] += 1
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
                if await _delete_with_retry(msg):
                    result["deleted"] += 1
                else:
                    result["failures"] += 1

            log.info(
                "Done. scanned=%d matched=%d deleted=%d skipped_pin=%d failures=%d",
                result["scanned"], result["matched"], result["deleted"],
                result["skipped_pin"], result["failures"],
            )
        except Exception as e:
            result["fatal_error"] = True
            log.exception("Cleanup failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)

    if result["fatal_error"]:
        return EXIT_PARTIAL
    if dry_run:
        return EXIT_OK
    # Partial: matched some but failed to delete at least one
    if result["matched"] > 0 and result["deleted"] < result["matched"]:
        log.error(
            "PARTIAL cleanup: deleted=%d of matched=%d (failures=%d)",
            result["deleted"], result["matched"], result["failures"],
        )
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="list only, do not delete")
    parser.add_argument(
        "--days",
        type=int,
        default=CLEANUP_LOOKBACK_DAYS,
        help=f"lookback window in days (default: {CLEANUP_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=HISTORY_LIMIT,
        help=f"max messages to scan per run (default: {HISTORY_LIMIT})",
    )
    args = parser.parse_args()
    exit_code = asyncio.run(
        run_cleanup(
            dry_run=args.dry_run,
            lookback_days=args.days,
            history_limit=args.history_limit,
        )
    )
    sys.exit(exit_code or EXIT_OK)

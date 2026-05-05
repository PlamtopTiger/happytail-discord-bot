"""
cleanup_bot_messages.py — ลบ message ของบอทเองทั้งหมดใน channel ที่ตั้งไว้ใน CHANNEL_ID
ใช้สำหรับเคลียร์ test message ก่อนเริ่มใช้งานจริง
"""
from __future__ import annotations

import asyncio
import logging
import os

import discord
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cleanup")

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0").strip())


async def run_cleanup():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            log.info("Logged in as %s", client.user)
            channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)

            deleted = 0
            async for msg in channel.history(limit=500):
                if msg.author.id == client.user.id:
                    try:
                        await msg.delete()
                        deleted += 1
                    except discord.HTTPException as e:
                        log.warning(f"Delete failed for msg {msg.id}: {e}")
            log.info(f"Cleaned up {deleted} bot messages")
        except Exception as e:
            log.exception("Cleanup failed: %s", e)
        finally:
            await client.close()

    await client.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(run_cleanup())

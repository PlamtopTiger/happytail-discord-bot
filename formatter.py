"""
formatter.py
แปลงข้อมูลจาก sheets_client เป็น Discord embed สวยๆ
"""
from __future__ import annotations

from datetime import date

import discord

# HAPPYTAIL pastel pink
EMBED_COLOR = 0xFFB6C1

THAI_MONTH_SHORT = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค.",
}

THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]


def thai_date(d: date, with_day: bool = False) -> str:
    """5 พ.ค. 2569 หรือ จันทร์ 5 พ.ค. 2569"""
    buddhist_year = d.year + 543
    base = f"{d.day} {THAI_MONTH_SHORT[d.month]} {buddhist_year}"
    if with_day:
        day_name = THAI_DAYS[d.weekday()]
        return f"{day_name} {base}"
    return base


def thai_date_relative(d: date, today: date) -> str:
    """วันนี้ / พรุ่งนี้ / [วัน] DD MMM"""
    delta = (d - today).days
    if delta == 0:
        return f"วันนี้ ({thai_date(d)})"
    if delta == 1:
        return f"พรุ่งนี้ ({thai_date(d)})"
    return thai_date(d, with_day=True)


# ==================== LIVE EMBEDS ====================
def embed_live_today(lives: list[dict], today: date) -> discord.Embed:
    """ตารางไลฟ์วันนี้ (auto-notify 18:00)"""
    embed = discord.Embed(
        title="ตารางไลฟ์วันนี้",
        description=f"{thai_date(today, with_day=True)}",
        color=EMBED_COLOR,
    )

    if not lives:
        embed.add_field(
            name="—",
            value="วันนี้ยังไม่มีตารางไลฟ์ค่ะ",
            inline=False,
        )
        return embed

    for live in lives:
        time_str = live["time"] or "—"
        platform = live["platform"] or "—"
        embed.add_field(
            name=f"{live['member']}",
            value=f"เวลา: {time_str}\nPlatform: {platform}",
            inline=True,
        )

    embed.set_footer(text="HAPPYTAIL Live Schedule")
    return embed


def embed_live_list(lives: list[dict], today: date) -> discord.Embed:
    """ตารางไลฟ์ตั้งแต่วันนี้เป็นต้นไป (slash /live)"""
    embed = discord.Embed(
        title="ตารางไลฟ์",
        description=f"ตั้งแต่ {thai_date(today)} เป็นต้นไป",
        color=EMBED_COLOR,
    )

    if not lives:
        embed.add_field(
            name="—",
            value="ยังไม่มีตารางไลฟ์ที่กำลังจะมาถึงค่ะ",
            inline=False,
        )
        return embed

    # group by date
    by_date: dict[date, list[dict]] = {}
    for live in lives:
        by_date.setdefault(live["date"], []).append(live)

    for d in sorted(by_date.keys()):
        lines = []
        for live in by_date[d]:
            time_str = live["time"] or "—"
            platform = live["platform"] or "—"
            lines.append(f"• **{live['member']}** — {time_str} ({platform})")
        embed.add_field(
            name=thai_date_relative(d, today),
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="HAPPYTAIL Live Schedule")
    return embed


# ==================== EVENT EMBEDS ====================
def embed_event_tomorrow(events_tomorrow: list[dict], tomorrow: date) -> discord.Embed:
    """ตารางงานพรุ่งนี้ (auto-notify 12:00)"""
    embed = discord.Embed(
        title="ตารางงานพรุ่งนี้",
        description=f"{thai_date(tomorrow, with_day=True)}",
        color=EMBED_COLOR,
    )

    if events_tomorrow:
        lines = [_format_event_line(e) for e in events_tomorrow]
        embed.add_field(
            name="—",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_field(
            name="—",
            value="พรุ่งนี้ไม่มีงานค่ะ",
            inline=False,
        )

    embed.set_footer(text="HAPPYTAIL Schedule")
    return embed


def embed_event_list(events: list[dict], today: date) -> discord.Embed:
    """ตารางงานทั้งหมด (slash /event)"""
    embed = discord.Embed(
        title="ตารางงาน HAPPYTAIL",
        description=f"ตั้งแต่ {thai_date(today)} เป็นต้นไป",
        color=EMBED_COLOR,
    )

    if not events:
        embed.add_field(
            name="—",
            value="ยังไม่มีงานที่กำลังจะมาถึงค่ะ",
            inline=False,
        )
        return embed

    by_date: dict[date, list[dict]] = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)

    for d in sorted(by_date.keys()):
        lines = [_format_event_line(e, with_name_bold=True) for e in by_date[d]]
        embed.add_field(
            name=thai_date_relative(d, today),
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="HAPPYTAIL Schedule")
    return embed


def _format_event_line(ev: dict, with_name_bold: bool = True) -> str:
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

    name_fmt = f"**{name}**" if with_name_bold else name
    line = f"• {name_fmt}\n  เวลา: {time_str} | สถานที่: {location}"

    members = ev.get("members") or []
    if members:
        line += f"\n  Member: {', '.join(members)}"

    return line

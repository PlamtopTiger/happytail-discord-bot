"""
sheets_client.py
Wrapper สำหรับ Google Sheets API — ดึงข้อมูล live schedule + events
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Iterable

import httplib2
import google_auth_httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# ========== CONSTANTS ==========
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Member whitelist (ไลฟ์) — sync กับ dropdown ใน Sheet (member + trainee + ชื่อวง)
ALLOWED_MEMBERS: set[str] = {
    "Aiyumu", "Bewji", "Beebelle", "Karin", "Marchi",
    "Ana", "Cutepid", "Maika", "Uta", "Zinzin",
    "HAPPYTAIL",
}

# Category whitelist (events)
ALLOWED_CATEGORIES: set[str] = {"งานแสดง", "งานโปรโมท", "งานออนไลน์"}

# Map เดือน (1-12) → ชื่อ tab ที่เป็นไปได้ใน sheet
# Sheet ของพี่นัทมี ~11 tab รายเดือน — สคริปต์จะลอง match จากชื่อ tab จริง
THAI_MONTHS = {
    1: ["มกราคม", "ม.ค.", "Jan", "January"],
    2: ["กุมภาพันธ์", "ก.พ.", "Feb", "February"],
    3: ["มีนาคม", "มี.ค.", "Mar", "March"],
    4: ["เมษายน", "เม.ย.", "Apr", "April"],
    5: ["พฤษภาคม", "พ.ค.", "May"],
    6: ["มิถุนายน", "มิ.ย.", "Jun", "June"],
    7: ["กรกฎาคม", "ก.ค.", "Jul", "July"],
    8: ["สิงหาคม", "ส.ค.", "Aug", "August"],
    9: ["กันยายน", "ก.ย.", "Sep", "Sept", "September"],
    10: ["ตุลาคม", "ต.ค.", "Oct", "October"],
    11: ["พฤศจิกายน", "พ.ย.", "Nov", "November"],
    12: ["ธันวาคม", "ธ.ค.", "Dec", "December"],
}


# ========== TIME-MERGE HELPERS ==========
def _parse_time_range(s: str):
    """Parse 'HH:MM - HH:MM' หรือ 'HH:MM เป็นต้นไป' → ((sh, sm), (eh, em) | None) | None"""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", s)
    if m:
        sh, sm, eh, em = map(int, m.groups())
        return ((sh, sm), (eh, em))
    m = re.match(r"^(\d{1,2}):(\d{2})\s*เป็นต้นไป", s)
    if m:
        sh, sm = map(int, m.groups())
        return ((sh, sm), None)
    return None


def _fmt_time(t) -> str:
    return f"{t[0]:02d}:{t[1]:02d}"


def merge_consecutive_lives(lives: list[dict]) -> list[dict]:
    """รวม time slot ที่ต่อกันของ member+platform เดียวกันในวันเดียวกัน

    เช่น
      [Aiyumu 21:30-22:30 Tiktok, Aiyumu 22:30 เป็นต้นไป Tiktok]
    → [Aiyumu 21:30 เป็นต้นไป Tiktok]
    """
    if len(lives) <= 1:
        return list(lives)

    # group by (date, member, platform) — keep insertion order
    groups: dict = {}
    order: list = []
    for live in lives:
        key = (live["date"], live["member"], live["platform"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(live)

    result = []
    for key in order:
        items = groups[key]
        if len(items) == 1:
            result.extend(items)
            continue

        parsed = [(_parse_time_range(it["time"]), it) for it in items]
        if any(p[0] is None for p in parsed):
            # parse ไม่ได้ — แสดงแยกตามเดิม
            result.extend(items)
            continue

        parsed.sort(key=lambda x: x[0][0])

        chains: list = []
        current = [parsed[0]]
        for i in range(1, len(parsed)):
            prev_end = current[-1][0][1]
            curr_start = parsed[i][0][0]
            if prev_end is not None and prev_end == curr_start:
                current.append(parsed[i])
            else:
                chains.append(current)
                current = [parsed[i]]
        chains.append(current)

        for chain in chains:
            if len(chain) == 1:
                result.append(chain[0][1])
                continue
            first_tr, first_item = chain[0]
            last_tr, _ = chain[-1]
            start = first_tr[0]
            end = last_tr[1]
            new_time = (
                f"{_fmt_time(start)} เป็นต้นไป"
                if end is None
                else f"{_fmt_time(start)} - {_fmt_time(end)}"
            )
            merged = dict(first_item)
            merged["time"] = new_time
            result.append(merged)

    return result


def _load_credentials(credentials_path: str) -> Credentials:
    """Load credentials from env vars (routine) or file (local dev)."""
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "")
    if private_key:
        info = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID", "happytail-bot"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID", ""),
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL", ""),
            "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "universe_domain": "googleapis.com",
        }
        logger.info("SheetsClient: loading credentials from env vars")
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    logger.info("SheetsClient: loading credentials from file: %s", credentials_path)
    return Credentials.from_service_account_file(credentials_path, scopes=SCOPES)


class SheetsClient:
    """Wrapper สำหรับ Google Sheets API"""

    def __init__(self, credentials_path: str, sheet_live_id: str, sheet_event_id: str):
        self.sheet_live_id = sheet_live_id
        self.sheet_event_id = sheet_event_id
        creds = _load_credentials(credentials_path)
        http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(disable_ssl_certificate_validation=True))
        self.service = build("sheets", "v4", http=http, cache_discovery=False)
        logger.info("SheetsClient initialized")

    # ==================== INTERNAL ====================
    def _list_tabs(self, spreadsheet_id: str) -> list[str]:
        """คืน list ของชื่อ tab ทั้งหมดใน spreadsheet"""
        meta = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def _resolve_month_tab(self, target: date) -> str | None:
        """หา tab ที่ตรงกับเดือนของ target date"""
        try:
            tabs = self._list_tabs(self.sheet_live_id)
        except HttpError as e:
            logger.error(f"List tabs failed: {e}")
            raise

        candidates = THAI_MONTHS.get(target.month, [])
        # match แบบ case-insensitive + substring
        for tab in tabs:
            tab_lower = tab.lower()
            for cand in candidates:
                if cand.lower() in tab_lower:
                    logger.info(f"Resolved month {target.month} -> tab '{tab}'")
                    return tab
        logger.warning(f"ไม่เจอ tab สำหรับเดือน {target.month} ใน {tabs}")
        return None

    def _read_range(self, spreadsheet_id: str, range_a1: str) -> list[list[str]]:
        try:
            res = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_a1)
                .execute()
            )
            return res.get("values", [])
        except HttpError as e:
            logger.error(f"Read range '{range_a1}' failed: {e}")
            raise

    @staticmethod
    def _row_get(row: list[str], idx: int) -> str:
        return row[idx].strip() if idx < len(row) and row[idx] else ""

    @staticmethod
    def _parse_date(s: str) -> date | None:
        """ลอง parse วันที่หลาย format"""
        if not s:
            return None
        s = s.strip()
        # ISO
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_day_or_date(s: str, default_year: int, default_month: int) -> date | None:
        """Parse full date หรือ day-number (เช่น "5" → date(default_year, default_month, 5))"""
        if not s:
            return None
        full = SheetsClient._parse_date(s)
        if full:
            return full
        try:
            day = int(s.strip())
            if 1 <= day <= 31:
                return date(default_year, default_month, day)
        except ValueError:
            pass
        return None

    # ==================== PUBLIC: LIVE ====================
    def get_lives_for_date(self, target: date) -> list[dict]:
        """ดึง live ของวันที่ target — return list of dict {member, date, time, platform}"""
        tab = self._resolve_month_tab(target)
        if tab is None:
            return []

        # Headers: Week | Date | (วัน) | Member | Time | Platform | Details | หมายเหตุ
        # เริ่มอ่านแถว 2 (ข้าม header)
        range_a1 = f"'{tab}'!A2:H1000"
        rows = self._read_range(self.sheet_live_id, range_a1)

        results: list[dict] = []
        last_date: date | None = None
        for row in rows:
            date_str = self._row_get(row, 1)  # column B = Date
            member = self._row_get(row, 3)    # column D = Member
            time_str = self._row_get(row, 4)  # column E = Time
            platform = self._row_get(row, 5)  # column F = Platform

            parsed = self._parse_day_or_date(date_str, target.year, target.month)
            if parsed is not None:
                last_date = parsed
            row_date = parsed if parsed is not None else last_date

            if member not in ALLOWED_MEMBERS:
                continue
            if row_date != target:
                continue

            # แปลง Discord -> Discord Membership
            display_platform = "Discord Membership" if platform.strip().lower() == "discord" else platform

            results.append({
                "member": member,
                "date": row_date,
                "time": time_str,
                "platform": display_platform,
            })

        merged = merge_consecutive_lives(results)
        logger.info(f"get_lives_for_date({target}) -> {len(results)} raw, {len(merged)} after merge")
        return merged

    # ==================== PUBLIC: EVENT ====================
    def get_events_for_dates(self, targets: Iterable[date]) -> list[dict]:
        """ดึง event ของวันใน targets — return list of dict {name, date, start, end, location}"""
        target_set = set(targets)
        if not target_set:
            return []

        # Tab: Events
        # Columns: id, date, name, location, category, startTime, endTime, createdBy, createdAt
        rows = self._read_range(self.sheet_event_id, "Events!A2:I10000")

        results: list[dict] = []
        for row in rows:
            date_str = self._row_get(row, 1)
            name = self._row_get(row, 2)
            location = self._row_get(row, 3)
            category = self._row_get(row, 4)
            start_time = self._row_get(row, 5)
            end_time = self._row_get(row, 6)

            if category not in ALLOWED_CATEGORIES:
                continue

            row_date = self._parse_date(date_str)
            if row_date is None or row_date not in target_set:
                continue

            results.append({
                "name": name,
                "date": row_date,
                "start": start_time,
                "end": end_time,
                "location": location,
                "category": category,
            })

        # sort by date then start time
        results.sort(key=lambda x: (x["date"], x["start"]))
        logger.info(f"get_events_for_dates({sorted(target_set)}) -> {len(results)} rows")
        return results

    def get_all_upcoming_events(self, today: date, limit: int = 20) -> list[dict]:
        """ดึง event ทั้งหมดตั้งแต่วันนี้เป็นต้นไป (สำหรับ /event command)"""
        rows = self._read_range(self.sheet_event_id, "Events!A2:I10000")

        results: list[dict] = []
        for row in rows:
            date_str = self._row_get(row, 1)
            name = self._row_get(row, 2)
            location = self._row_get(row, 3)
            category = self._row_get(row, 4)
            start_time = self._row_get(row, 5)
            end_time = self._row_get(row, 6)

            if category not in ALLOWED_CATEGORIES:
                continue

            row_date = self._parse_date(date_str)
            if row_date is None or row_date < today:
                continue

            results.append({
                "name": name,
                "date": row_date,
                "start": start_time,
                "end": end_time,
                "location": location,
                "category": category,
            })

        results.sort(key=lambda x: (x["date"], x["start"]))
        return results[:limit]

    def get_lives_for_month(self, target: date, today: date) -> list[dict]:
        """ดึง live ทั้งหมดของเดือน target ตั้งแต่ today เป็นต้นไป (สำหรับ /live command)"""
        tab = self._resolve_month_tab(target)
        if tab is None:
            return []

        range_a1 = f"'{tab}'!A2:H1000"
        rows = self._read_range(self.sheet_live_id, range_a1)

        results: list[dict] = []
        last_date: date | None = None
        for row in rows:
            date_str = self._row_get(row, 1)
            member = self._row_get(row, 3)
            time_str = self._row_get(row, 4)
            platform = self._row_get(row, 5)

            parsed = self._parse_day_or_date(date_str, target.year, target.month)
            if parsed is not None:
                last_date = parsed
            row_date = parsed if parsed is not None else last_date

            if member not in ALLOWED_MEMBERS:
                continue
            if row_date is None or row_date < today:
                continue

            display_platform = "Discord Membership" if platform.strip().lower() == "discord" else platform

            results.append({
                "member": member,
                "date": row_date,
                "time": time_str,
                "platform": display_platform,
            })

        results.sort(key=lambda x: (x["date"], x["member"]))
        return merge_consecutive_lives(results)

"""
app_client.py
Wrapper สำหรับ HAPPYTAIL App API (/api/bot/...)
ใช้แทน Google Sheets สำหรับการดึง events (งานแสดง/งานโปรโมท)

NOTE: ไลฟ์ (Live) ยังคงใช้ SheetsClient — ไฟล์นี้ไม่แตะ Live data
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10  # seconds


class AppClient:
    """Wrapper สำหรับ HAPPYTAIL App API"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        logger.info("AppClient initialized (base=%s)", self.base_url)

    # ==================== INTERNAL ====================
    def _get(self, path: str, params: dict | None = None) -> dict | None:
        url = f"{self.base_url}{path}"
        try:
            res = requests.get(
                url,
                headers=self._headers,
                params=params or {},
                timeout=DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error("AppClient GET %s failed: %s", url, e)
            return None

        if res.status_code != 200:
            logger.error(
                "AppClient GET %s returned %d: %s",
                url, res.status_code, res.text[:200],
            )
            return None

        try:
            return res.json()
        except ValueError as e:
            logger.error("AppClient GET %s invalid JSON: %s", url, e)
            return None

    @staticmethod
    def _adapt_event(raw: dict, fallback_date: str | None = None) -> dict:
        """แปลง event จาก API → dict shape ที่ formatter.py ใช้

        formatter.py ต้องการ keys:
          name, date (date object), start, end, location, category, members
        """
        date_str = raw.get("date") or fallback_date or ""
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
        except ValueError:
            logger.warning("Invalid date string: %r", date_str)
            d = None

        all_day = bool(raw.get("all_day"))
        start = raw.get("start_time") or ""
        end = raw.get("end_time") or ""
        if all_day:
            # User: event แจ้งแฟนคลับไม่จำเป็นต้องมีเวลา
            start = ""
            end = ""

        members_raw = raw.get("members") or []
        if isinstance(members_raw, str):
            members = [m.strip() for m in members_raw.split(",") if m.strip()]
        else:
            members = list(members_raw)

        return {
            "name": raw.get("name") or "",
            "date": d,
            "start": start,
            "end": end,
            "location": raw.get("location") or "",
            "category": raw.get("category") or "",
            "members": members,
        }

    # ==================== PUBLIC ====================
    def get_events_for_date(
        self,
        target: date,
        categories: Iterable[str] | None = None,
    ) -> list[dict]:
        """ดึง events ของวันที่ target

        Args:
            target: วันที่
            categories: list ของ category (default = ใช้ค่า server)
                       Discord bot ใช้ ["งานแสดง", "งานโปรโมท"]

        Returns:
            list ของ event dict — empty list ถ้า error
        """
        params = {"date": target.isoformat()}
        if categories:
            params["categories"] = ",".join(categories)

        data = self._get("/api/bot/events", params=params)
        if data is None:
            return []

        date_str = data.get("date") or target.isoformat()
        events = data.get("events") or []
        adapted = [self._adapt_event(e, fallback_date=date_str) for e in events]
        # filter out events with no parseable date
        adapted = [e for e in adapted if e["date"] is not None]
        logger.info(
            "AppClient.get_events_for_date(%s) -> %d rows", target, len(adapted)
        )
        return adapted

    def get_events_for_dates(
        self,
        targets: Iterable[date],
        categories: Iterable[str] | None = None,
    ) -> list[dict]:
        """Backward-compat: ดึง events หลายวัน (รวมเป็น list เดียว)

        ใช้ได้กับ scheduler.py เดิมที่เรียก get_events_for_dates([date])
        """
        results: list[dict] = []
        for d in targets:
            results.extend(self.get_events_for_date(d, categories=categories))
        return results

    def get_upcoming_events(
        self,
        days: int = 14,
        categories: Iterable[str] | None = None,
    ) -> list[dict]:
        """ดึง events ตั้งแต่วันนี้ → +N วัน"""
        params: dict = {"days": days}
        if categories:
            params["categories"] = ",".join(categories)

        data = self._get("/api/bot/events/upcoming", params=params)
        if data is None:
            return []

        events = data.get("events") or []
        adapted = [self._adapt_event(e) for e in events]
        adapted = [e for e in adapted if e["date"] is not None]
        logger.info(
            "AppClient.get_upcoming_events(days=%d) -> %d rows", days, len(adapted)
        )
        return adapted

    def get_all_upcoming_events(
        self,
        today: date,
        limit: int = 20,
        categories: Iterable[str] | None = None,
        days: int = 60,
    ) -> list[dict]:
        """Backward-compat: replacement สำหรับ SheetsClient.get_all_upcoming_events

        ดึง events ตั้งแต่ today จำนวน `days` วันข้างหน้า แล้ว limit
        """
        events = self.get_upcoming_events(days=days, categories=categories)
        # filter events ที่ < today (กันเหลือ)
        events = [e for e in events if e["date"] and e["date"] >= today]
        events.sort(key=lambda x: (x["date"], x.get("start") or ""))
        return events[:limit]

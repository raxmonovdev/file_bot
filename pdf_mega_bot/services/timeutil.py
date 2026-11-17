"""Vaqt Toshkent bo'yicha, bazada esa UTC (soat mintaqasiz) saqlanadi."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tashkent")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today():
    return datetime.now(TZ).date()


def midnight_utc() -> datetime:
    now = datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    local = value.replace(tzinfo=timezone.utc).astimezone(TZ)
    return local.strftime("%Y-%m-%d %H:%M")

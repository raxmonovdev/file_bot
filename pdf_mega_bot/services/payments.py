"""Tariflar va Stars to'lov kodi."""

from __future__ import annotations

from config import Plan, settings
from services.i18n import t


def find_plan(days: int) -> Plan | None:
    for plan in settings.plans:
        if plan.days == days:
            return plan
    return None


def format_som(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def plan_title(lang: str | None, days: int) -> str:
    key = {30: "plan_30", 90: "plan_90", 365: "plan_365"}.get(days, "")
    if key:
        return t(lang, key)
    return t(lang, "plan_days", days=days)


def make_payload(days: int, telegram_id: int) -> str:
    return f"p:{days}:{telegram_id}"


def parse_payload(payload: str) -> tuple[Plan, int] | None:
    try:
        kind, days_raw, user_raw = payload.split(":")
        if kind != "p":
            return None
        days = int(days_raw)
        telegram_id = int(user_raw)
    except (ValueError, AttributeError):
        return None
    plan = find_plan(days)
    if plan is None:
        return None
    return plan, telegram_id

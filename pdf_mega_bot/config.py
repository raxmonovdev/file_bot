"""Sozlamalar .env fayldan o'qiladi. Token kodda turmaydi."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Plan:
    days: int
    stars: int
    uzs: int


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def _plans() -> tuple[Plan, ...]:
    raw = os.getenv("PREMIUM_PLANS", "30:150:20000,90:400:50000,365:1200:150000")
    plans: list[Plan] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        days, stars, uzs = chunk.split(":")
        plans.append(Plan(int(days), int(stars), int(uzs)))
    if not plans:
        raise RuntimeError("PREMIUM_PLANS bo'sh. Masalan: 30:150:20000")
    return tuple(plans)


def _admin_ids() -> tuple[int, ...]:
    raw = os.getenv("ADMIN_IDS", "")
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return tuple(ids)


def _admin_usernames() -> frozenset[str]:
    raw = os.getenv("ADMIN_USERNAMES", "raxmonovdev")
    names: set[str] = set()
    for part in raw.split(","):
        name = part.strip().lstrip("@").lower()
        if name:
            names.add(name)
    return frozenset(names)


class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    admin_ids: tuple[int, ...] = _admin_ids()
    admin_usernames: frozenset[str] = _admin_usernames()
    card_number: str = os.getenv("CARD_NUMBER", "").strip()
    card_holder: str = os.getenv("CARD_HOLDER", "").strip()
    plans: tuple[Plan, ...] = _plans()
    free_daily_limit: int = _int("FREE_DAILY_LIMIT", 3)
    free_max_mb: int = _int("FREE_MAX_MB", 10)
    premium_max_mb: int = _int("PREMIUM_MAX_MB", 20)
    convert_timeout: int = _int("CONVERT_TIMEOUT", 60)
    queue_slots: int = _int("QUEUE_SLOTS", 2)
    rate_limit: int = _int("RATE_LIMIT", 20)
    max_merge_files: int = _int("MAX_MERGE_FILES", 15)
    max_images: int = _int("MAX_IMAGES", 20)
    max_image_pages: int = _int("MAX_IMAGE_PAGES", 30)
    watermark_text: str = os.getenv("WATERMARK_TEXT", "PDF Mega Bot").strip() or "PDF Mega Bot"
    soffice_path: str = os.getenv("SOFFICE_PATH", "").strip()
    temp_dir: Path = BASE_DIR / "temp"
    log_path: Path = BASE_DIR / "logs" / "bot.log"
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'bot.db'}",
    )


settings = Settings()
(settings.temp_dir).mkdir(parents=True, exist_ok=True)
(settings.log_path.parent).mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

"""Kunlik limit va premium holati."""

from __future__ import annotations

from config import settings
from database.models import User
from services.timeutil import utcnow


def is_premium(user: User) -> bool:
    return bool(user.premium_until and user.premium_until > utcnow())


def max_bytes_for(user: User) -> int:
    mb = settings.premium_max_mb if is_premium(user) else settings.free_max_mb
    return mb * 1024 * 1024


def max_mb_for(user: User) -> int:
    return settings.premium_max_mb if is_premium(user) else settings.free_max_mb

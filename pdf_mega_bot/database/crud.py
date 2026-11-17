"""Foydalanuvchi, limit, to'lov va admin yozuvlari."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Admin, Payment, Usage, User
from services.limits import is_premium
from services.timeutil import midnight_utc, today, utcnow


def refresh_premium(user: User) -> None:
    user.is_premium = is_premium(user)


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        refresh_premium(user)
    return user


async def ensure_admin_premium(session: AsyncSession, user: User) -> None:
    """Admin uchun premium o'zi yoniq turadi, muddati tugamasligi uchun uzaytiriladi."""
    name = (user.username or "").lower()
    configured = name in settings.admin_usernames or user.telegram_id in settings.admin_ids
    if not configured and not await is_admin(session, user.telegram_id):
        return
    if configured:
        await sync_admins(session, (user.telegram_id,))
    horizon = utcnow() + timedelta(days=3650)
    if user.premium_until is None or user.premium_until < utcnow() + timedelta(days=365):
        user.premium_until = horizon
        user.reminder_until = horizon
    user.is_premium = True
    await session.flush()


async def activate_admin_premiums(session: AsyncSession) -> None:
    result = await session.execute(select(User))
    for user in result.scalars():
        await ensure_admin_premium(session, user)


async def upsert_user(session: AsyncSession, telegram_id: int, username: str | None) -> User:
    user = await get_user(session, telegram_id)
    if user is None:
        user = User(telegram_id=telegram_id, username=username, language=None, created_at=utcnow())
        session.add(user)
        await session.flush()
    else:
        user.username = username
    await ensure_admin_premium(session, user)
    return user


async def get_or_create_id(session: AsyncSession, telegram_id: int) -> User:
    user = await get_user(session, telegram_id)
    if user:
        return user
    user = User(telegram_id=telegram_id, language=None, created_at=utcnow())
    session.add(user)
    await session.flush()
    return user


async def today_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(Usage.count), 0)).where(
            Usage.user_id == user_id,
            Usage.date == today(),
        )
    )
    return int(result.scalar_one())


async def add_usage(session: AsyncSession, user_id: int, action: str) -> None:
    day = today()
    result = await session.execute(
        select(Usage).where(Usage.user_id == user_id, Usage.date == day, Usage.action_type == action)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(Usage(user_id=user_id, date=day, action_type=action, count=1))
    else:
        row.count += 1
    await session.flush()


async def grant_premium(session: AsyncSession, user: User, days: int) -> datetime:
    base = user.premium_until if user.premium_until and user.premium_until > utcnow() else utcnow()
    user.premium_until = base + timedelta(days=days)
    user.is_premium = True
    user.reminder_until = None
    await session.flush()
    return user.premium_until


async def revoke_premium(session: AsyncSession, user: User) -> None:
    user.premium_until = None
    user.is_premium = False
    user.reminder_until = None
    await session.flush()


async def payment_by_external(session: AsyncSession, external_id: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.external_id == external_id))
    return result.scalar_one_or_none()


async def add_payment(session: AsyncSession, **fields) -> Payment:
    payment = Payment(**fields)
    session.add(payment)
    await session.flush()
    return payment


async def get_payment(session: AsyncSession, payment_id: int) -> tuple[Payment, User] | None:
    result = await session.execute(
        select(Payment, User).join(User, Payment.user_id == User.id).where(Payment.id == payment_id)
    )
    row = result.first()
    return (row[0], row[1]) if row else None


async def pending_payments(session: AsyncSession, limit: int = 10) -> list[tuple[Payment, User]]:
    result = await session.execute(
        select(Payment, User)
        .join(User, Payment.user_id == User.id)
        .where(Payment.status == "pending")
        .order_by(Payment.created_at)
        .limit(limit)
    )
    return list(result.all())


async def sync_admins(session: AsyncSession, telegram_ids: tuple[int, ...]) -> None:
    for telegram_id in telegram_ids:
        result = await session.execute(select(Admin).where(Admin.telegram_id == telegram_id))
        if result.scalar_one_or_none() is None:
            session.add(Admin(telegram_id=telegram_id))
    await session.flush()


async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(select(Admin.id).where(Admin.telegram_id == telegram_id))
    return result.scalar_one_or_none() is not None


async def admin_ids(session: AsyncSession) -> set[int]:
    result = await session.execute(select(Admin.telegram_id))
    return set(result.scalars().all())


async def stats(session: AsyncSession) -> dict:
    total = int((await session.execute(select(func.count()).select_from(User))).scalar_one())
    new_today = int(
        (
            await session.execute(
                select(func.count()).select_from(User).where(User.created_at >= midnight_utc())
            )
        ).scalar_one()
    )
    active = int(
        (
            await session.execute(
                select(func.count(func.distinct(Usage.user_id))).where(Usage.date == today())
            )
        ).scalar_one()
    )
    premium = int(
        (
            await session.execute(
                select(func.count()).select_from(User).where(User.premium_until.is_not(None), User.premium_until > utcnow())
            )
        ).scalar_one()
    )
    stars = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == "approved", Payment.method == "stars"
                )
            )
        ).scalar_one()
    )
    card = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.status == "approved", Payment.method == "card"
                )
            )
        ).scalar_one()
    )
    top_rows = await session.execute(
        select(Usage.action_type, func.sum(Usage.count))
        .group_by(Usage.action_type)
        .order_by(func.sum(Usage.count).desc())
        .limit(8)
    )
    return {
        "total": total,
        "new": new_today,
        "active": active,
        "premium": premium,
        "stars": stars,
        "card": card,
        "top": list(top_rows.all()),
    }


async def list_telegram_ids(session: AsyncSession, audience: str) -> list[int]:
    stmt = select(User.telegram_id)
    now = utcnow()
    if audience == "premium":
        stmt = stmt.where(User.premium_until.is_not(None), User.premium_until > now)
    elif audience == "free":
        stmt = stmt.where(or_(User.premium_until.is_(None), User.premium_until <= now))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def users_to_remind(session: AsyncSession) -> list[User]:
    now = utcnow()
    soon = now + timedelta(days=3)
    result = await session.execute(
        select(User).where(
            User.premium_until.is_not(None),
            User.premium_until > now,
            User.premium_until <= soon,
            or_(User.reminder_until.is_(None), User.reminder_until != User.premium_until),
        )
    )
    return list(result.scalars().all())

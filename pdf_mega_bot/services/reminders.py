"""Premium tugashiga 3 kun qolganda bir marta eslatma."""

from __future__ import annotations

import logging

from aiogram import Bot

from database.crud import users_to_remind
from database.db import Session
from services.i18n import t
from services.timeutil import format_dt

logger = logging.getLogger(__name__)


async def remind_expiring(bot: Bot) -> None:
    async with Session() as session:
        users = await users_to_remind(session)
        for user in users:
            try:
                await bot.send_message(
                    user.telegram_id,
                    t(user.language, "reminder", date=format_dt(user.premium_until)),
                )
            except Exception:
                logger.exception("Eslatma yuborilmadi: %s", user.telegram_id)
                continue
            user.reminder_until = user.premium_until
        await session.commit()

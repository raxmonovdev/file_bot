"""Har bir xabar oldidan foydalanuvchini bazaga yozish va spamni to'xtatish."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import settings
from database.crud import upsert_user
from database.db import Session
from keyboards.common import language_kb
from services.i18n import t


class ContextMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.hits: dict[int, deque[float]] = defaultdict(deque)

    def _throttled(self, user_id: int) -> bool:
        now = time.monotonic()
        bucket = self.hits[user_id]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit:
            return True
        bucket.append(now)
        return False

    async def __call__(self, handler, event: TelegramObject, data: dict):
        if isinstance(event, Message) and event.chat.type != "private":
            return None
        if isinstance(event, CallbackQuery) and event.message is not None:
            chat = getattr(event.message, "chat", None)
            if chat is not None and chat.type != "private":
                return None

        user = getattr(event, "from_user", None)
        async with Session() as session:
            data["session"] = session
            db_user = None
            if user is not None:
                db_user = await upsert_user(session, user.id, user.username)
                data["db_user"] = db_user
                data["lang"] = db_user.language
                paid = isinstance(event, Message) and event.successful_payment is not None
                if not paid and self._throttled(user.id):
                    if isinstance(event, CallbackQuery):
                        await event.answer(t(db_user.language, "rate_limit"), show_alert=True)
                    elif isinstance(event, Message):
                        await event.answer(t(db_user.language, "rate_limit"))
                    await session.commit()
                    return None
                if db_user.language is None and not paid and not _language_step(event):
                    if isinstance(event, CallbackQuery):
                        await event.answer()
                        await event.bot.send_message(user.id, t("uz", "choose_language"), reply_markup=language_kb())
                    elif isinstance(event, Message):
                        await event.answer(t("uz", "choose_language"), reply_markup=language_kb())
                    await session.commit()
                    return None
            try:
                result = await handler(event, data)
            except SkipHandler:
                await session.commit()
                raise
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()
                return result


def _language_step(event: TelegramObject) -> bool:
    if isinstance(event, Message) and event.text and event.text.startswith("/start"):
        return True
    if isinstance(event, CallbackQuery) and event.data and event.data.startswith("lang:"):
        return True
    return False

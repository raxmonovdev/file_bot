"""Eski tugma bosilsa, jim qolmasin."""

from aiogram import Router
from aiogram.types import CallbackQuery

from services.i18n import t

router = Router()


@router.callback_query()
async def stale_button(callback: CallbackQuery, lang: str | None) -> None:
    await callback.answer(t(lang, "stale_button"), show_alert=True)

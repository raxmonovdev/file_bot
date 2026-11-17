"""PDF ↔ Word va rasm ↔ PDF."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from handlers.runtime import append_collected, ask_for, chat_id_of, info_from_message, run_job, stored_info, take_file
from services.i18n import done_words, t
from states.states import CONVERT_ACTIONS, Flow

router = Router()
WORDS = done_words()


@router.callback_query(F.data.startswith("go:"))
async def go_convert(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    action = (callback.data or "").split(":", 1)[1]
    if action not in CONVERT_ACTIONS:
        raise SkipHandler()
    await callback.answer()
    await ask_for(callback.bot, chat_id_of(callback), state, lang, action)


@router.callback_query(Flow.choose_action, F.data.startswith("do:"))
async def do_convert(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    action = (callback.data or "").split(":", 1)[1]
    if action not in CONVERT_ACTIONS:
        raise SkipHandler()
    info = stored_info(await state.get_data())
    await callback.answer()
    await take_file(callback.bot, chat_id_of(callback), state, session, db_user, lang, action, info)


@router.message(Flow.collect_images, F.photo | F.document)
async def add_image(message: Message, state: FSMContext, db_user: User, lang: str | None) -> None:
    info = info_from_message(message)
    if info is None:
        return
    await append_collected(message.bot, message.chat.id, state, db_user, lang, info, images=True)


@router.message(Flow.collect_images, F.text)
async def images_text(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    if (message.text or "").strip().lower() not in WORDS:
        await message.answer(t(lang, "ask_images"))
        return
    await finish_images(message.bot, message.chat.id, state, session, db_user, lang)


@router.callback_query(Flow.collect_images, F.data == "collect:images")
async def images_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    await finish_images(callback.bot, chat_id_of(callback), state, session, db_user, lang, callback)


async def finish_images(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str | None,
    callback: CallbackQuery | None = None,
) -> None:
    files = list((await state.get_data()).get("files") or [])
    if not files:
        if callback is not None:
            await callback.answer(t(lang, "need_one_image"), show_alert=True)
        else:
            await bot.send_message(chat_id, t(lang, "need_one_image"))
        return
    if callback is not None:
        await callback.answer()
    await state.clear()
    await run_job(bot, chat_id, session, user, lang, "img2pdf", files)

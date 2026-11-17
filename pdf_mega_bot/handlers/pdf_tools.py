"""Birlashtirish, bo'lish, siqish, sahifani o'chirish va burish."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from handlers.runtime import (
    append_collected,
    ask_for,
    chat_id_of,
    info_from_message,
    peek_pages,
    run_job,
    stored_info,
    take_file,
)
from services.errors import UserFacingError
from services.i18n import done_words, t
from services.pdf_service import parse_pages
from states.states import TOOL_ACTIONS, Flow

router = Router()
WORDS = done_words()
PAGE_ACTIONS = {"split", "delete", "rotate"}


@router.callback_query(F.data.startswith("go:"))
async def go_tool(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    action = (callback.data or "").split(":", 1)[1]
    if action not in TOOL_ACTIONS:
        raise SkipHandler()
    await callback.answer()
    await ask_for(callback.bot, chat_id_of(callback), state, lang, action)


@router.callback_query(Flow.choose_action, F.data.startswith("do:"))
async def do_tool(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    action = (callback.data or "").split(":", 1)[1]
    if action not in TOOL_ACTIONS:
        raise SkipHandler()
    info = stored_info(await state.get_data())
    await callback.answer()
    await take_file(callback.bot, chat_id_of(callback), state, session, db_user, lang, action, info)


@router.message(Flow.collect_merge, F.document)
async def add_pdf(message: Message, state: FSMContext, db_user: User, lang: str | None) -> None:
    info = info_from_message(message)
    if info is None:
        return
    await append_collected(message.bot, message.chat.id, state, db_user, lang, info, images=False)


@router.message(Flow.collect_merge, F.text)
async def merge_text(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    if (message.text or "").strip().lower() not in WORDS:
        await message.answer(t(lang, "ask_merge"))
        return
    await finish_merge(message.bot, message.chat.id, state, session, db_user, lang)


@router.callback_query(Flow.collect_merge, F.data == "collect:merge")
async def merge_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    await finish_merge(callback.bot, chat_id_of(callback), state, session, db_user, lang, callback)


async def finish_merge(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str | None,
    callback: CallbackQuery | None = None,
) -> None:
    files = list((await state.get_data()).get("files") or [])
    if len(files) < 2:
        if callback is not None:
            await callback.answer(t(lang, "need_two_pdf"), show_alert=True)
        else:
            await bot.send_message(chat_id, t(lang, "need_two_pdf"))
        return
    if callback is not None:
        await callback.answer()
    await state.clear()
    await run_job(bot, chat_id, session, user, lang, "merge", files)


@router.callback_query(Flow.wait_angle, F.data.startswith("angle:"))
async def pick_angle(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    try:
        angle = int((callback.data or "").split(":")[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    if angle not in {90, 180, 270}:
        await callback.answer()
        return
    await state.update_data(angle=angle)
    await state.set_state(Flow.wait_pages)
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_pages_rotate"))


@router.message(Flow.wait_pages, F.text)
async def on_pages(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    data = await state.get_data()
    action = str(data.get("action") or "")
    if action not in PAGE_ACTIONS:
        return
    info = stored_info(data)
    try:
        total = await peek_pages(message.bot, info, db_user)
    except UserFacingError as exc:
        await state.clear()
        await message.answer(t(lang, exc.key, **exc.params))
        return
    pages = parse_pages(message.text or "", total)
    if pages is None:
        await message.answer(t(lang, "bad_pages", total=total))
        return
    if action == "delete" and len(pages) >= total:
        await message.answer(t(lang, "keep_one"))
        return
    angle = data.get("angle")
    await state.clear()
    await run_job(
        message.bot,
        message.chat.id,
        session,
        db_user,
        lang,
        action,
        [info],
        pages=pages,
        angle=int(angle) if angle else None,
    )

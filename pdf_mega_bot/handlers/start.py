"""Boshlash, menyu, profil va yordam."""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import today_count
from database.models import User
from handlers.runtime import chat_id_of, esc, info_from_message
from keyboards.common import (
    convert_menu_kb,
    edit_menu_kb,
    language_kb,
    main_kb,
    premium_kb,
    tools_menu_kb,
)
from services.files import delete_thumb
from services.i18n import cancel_texts, menu_text_to_key, t
from services.limits import is_premium
from services.payments import format_som, plan_title
from services.timeutil import format_dt
from states.states import INPUT_STATES, Flow

router = Router()
MENU = menu_text_to_key()
CANCELS = cancel_texts()


async def reset_flow(state: FSMContext, user_id: int) -> None:
    await state.clear()
    delete_thumb(user_id)


async def send_welcome(message: Message, lang: str, name: str) -> None:
    await message.answer(t(lang, "welcome", name=esc(name)), reply_markup=main_kb(lang))


async def send_profile(message: Message, session: AsyncSession, user: User, lang: str) -> None:
    used = await today_count(session, user.id)
    if is_premium(user):
        usage = t(lang, "usage_unlimited", used=used)
        status = t(lang, "status_premium")
        until = format_dt(user.premium_until)
    else:
        usage = t(lang, "usage_limited", used=used, limit=settings.free_daily_limit)
        status = t(lang, "status_free")
        until = "—"
    username = f"@{escape(user.username)}" if user.username else "—"
    await message.answer(
        t(
            lang,
            "profile",
            tid=user.telegram_id,
            username=username,
            language=t(lang, f"lang_{user.language or 'uz'}"),
            status=status,
            until=until,
            used=usage,
        ),
        reply_markup=main_kb(lang),
    )


async def send_premium(message: Message, lang: str) -> None:
    lines = [
        t(
            lang,
            "premium_intro",
            limit=settings.free_daily_limit,
            free_mb=settings.free_max_mb,
            prem_mb=settings.premium_max_mb,
        )
    ]
    for plan in settings.plans:
        lines.append(
            t(
                lang,
                "premium_plan_line",
                plan=plan_title(lang, plan.days),
                stars=plan.stars,
                uzs=format_som(plan.uzs),
            )
        )
    await message.answer("\n".join(lines), reply_markup=premium_kb(lang))


async def send_help(message: Message, lang: str) -> None:
    await message.answer(
        t(lang, "help", limit=settings.free_daily_limit, free_mb=settings.free_max_mb, prem_mb=settings.premium_max_mb),
        reply_markup=main_kb(lang),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_user: User, lang: str | None) -> None:
    await reset_flow(state, db_user.telegram_id)
    if not db_user.language:
        await message.answer(t("uz", "choose_language"), reply_markup=language_kb())
        return
    await send_welcome(message, db_user.language, message.from_user.first_name or "")


@router.callback_query(F.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    code = (callback.data or "").split(":", 1)[1]
    if code not in {"uz", "ru", "en"}:
        await callback.answer()
        return
    db_user.language = code
    await reset_flow(state, db_user.telegram_id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await send_welcome(callback.message, code, callback.from_user.first_name or "")
    else:
        await callback.bot.send_message(
            callback.from_user.id,
            t(code, "welcome", name=esc(callback.from_user.first_name or "")),
            reply_markup=main_kb(code),
        )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    await message.answer(t(lang, "welcome", name=esc(message.from_user.first_name or "")), reply_markup=main_kb(lang))


@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    await send_profile(message, session, db_user, lang)


@router.message(Command("premium"))
async def cmd_premium(message: Message, state: FSMContext, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    await send_premium(message, lang)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    await send_help(message, lang)


@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    await message.answer(t(lang, "choose_language"), reply_markup=language_kb())


@router.message(Command("cancel"))
@router.callback_query(F.data == "flow:cancel")
async def cancel(event: Message | CallbackQuery, state: FSMContext, db_user: User, lang: str) -> None:
    await reset_flow(state, db_user.telegram_id)
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.bot.send_message(chat_id_of(event), t(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    await event.answer(t(lang, "cancelled"), reply_markup=main_kb(lang))


@router.message(F.text)
async def on_text(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        from aiogram.dispatcher.event.bases import SkipHandler

        raise SkipHandler()
    current = await state.get_state()
    if text in CANCELS:
        await reset_flow(state, db_user.telegram_id)
        await message.answer(t(lang, "cancelled"), reply_markup=main_kb(lang))
        return
    if current in INPUT_STATES:
        from aiogram.dispatcher.event.bases import SkipHandler

        raise SkipHandler()
    key = MENU.get(text)
    if key:
        await reset_flow(state, db_user.telegram_id)
        if key == "btn_convert":
            await message.answer(t(lang, "convert_menu"), reply_markup=convert_menu_kb(lang))
        elif key == "btn_edit":
            await message.answer(t(lang, "edit_menu"), reply_markup=edit_menu_kb(lang))
        elif key == "btn_merge_split":
            await message.answer(t(lang, "tools_menu"), reply_markup=tools_menu_kb(lang))
        elif key == "btn_compress":
            from handlers.runtime import ask_for

            await ask_for(message.bot, message.chat.id, state, lang, "compress")
        elif key == "btn_profile":
            await send_profile(message, session, db_user, lang)
        elif key == "btn_premium":
            await send_premium(message, lang)
        elif key == "btn_help":
            await send_help(message, lang)
        return
    if current == Flow.choose_action.state:
        await message.answer(t(lang, "choose_action_hint"))
        return
    if current is not None:
        from aiogram.dispatcher.event.bases import SkipHandler

        raise SkipHandler()
    await message.answer(t(lang, "unknown"), reply_markup=main_kb(lang))


@router.message(F.photo | F.document)
async def incoming_file(message: Message, state: FSMContext, db_user: User, lang: str) -> None:
    current = await state.get_state()
    if current not in {None, Flow.choose_action.state, Flow.edit_menu.state}:
        from aiogram.dispatcher.event.bases import SkipHandler

        raise SkipHandler()
    info = info_from_message(message)
    if info is None:
        return
    from services.limits import max_bytes_for, max_mb_for

    size = int(info["file_size"] or 0)
    if size and size > max_bytes_for(db_user):
        await message.answer(t(lang, "file_too_big", max_mb=max_mb_for(db_user)))
        return
    from pathlib import Path

    from keyboards.common import file_drop_kb

    delete_thumb(db_user.telegram_id)
    ext = Path(str(info["file_name"])).suffix
    await state.set_state(Flow.edit_menu)
    await state.update_data(ext=ext, thumb=False, from_drop=True, clear_icon=False, **info)
    await message.answer(
        t(lang, "file_ready", name=esc(info["file_name"])),
        reply_markup=file_drop_kb(lang),
    )

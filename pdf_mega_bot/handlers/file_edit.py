"""Fayl nomi va Telegramdagi kichik rasm (thumbnail)."""

from __future__ import annotations

import io
import logging
import uuid
from html import escape
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import add_usage, today_count
from database.models import User
from handlers.runtime import _download, busy, chat_id_of, limit_line, stored_info
from keyboards.common import auto_names_kb, edit_kb, file_drop_kb, premium_kb
from services.errors import UserFacingError
from services.files import auto_names, blank_thumbnail, delete_thumb, make_thumbnail, safe_filename, thumb_file
from services.i18n import t
from services.limits import is_premium
from states.states import Flow

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "go:edit")
async def go_edit(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    from handlers.runtime import ask_for

    await callback.answer()
    await ask_for(callback.bot, chat_id_of(callback), state, lang, "edit")


@router.callback_query(Flow.choose_action, F.data == "do:edit")
async def do_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    from handlers.runtime import take_file

    info = stored_info(await state.get_data())
    await callback.answer()
    await take_file(callback.bot, chat_id_of(callback), state, session, db_user, lang, "edit", info)


async def show_drop_menu(bot, chat_id: int, state: FSMContext, lang: str | None) -> None:
    data = await state.get_data()
    await state.set_state(Flow.edit_menu)
    await bot.send_message(
        chat_id,
        t(lang, "file_ready", name=escape(str(data.get("file_name") or "fayl"))),
        reply_markup=file_drop_kb(lang),
    )


@router.callback_query(Flow.edit_menu, F.data == "file:menu")
async def file_menu(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await callback.answer()
    await show_drop_menu(callback.bot, chat_id_of(callback), state, lang)


@router.callback_query(Flow.edit_menu, F.data == "file:icon")
async def change_icon(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    await state.set_state(Flow.edit_thumb)
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_thumb"))


@router.callback_query(Flow.edit_menu, F.data == "file:auto")
async def show_auto_names(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    data = await state.get_data()
    names = auto_names(str(data.get("file_name") or "fayl"), str(data.get("ext") or ""))
    await state.update_data(auto_names=names)
    await callback.answer()
    await callback.bot.send_message(
        chat_id_of(callback),
        t(lang, "auto_title"),
        reply_markup=auto_names_kb(lang, names),
    )


@router.callback_query(Flow.edit_menu, F.data.startswith("file:pick:"))
async def pick_auto_name(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    data = await state.get_data()
    names = list(data.get("auto_names") or [])
    try:
        index = int((callback.data or "").rsplit(":", 1)[1])
        chosen = names[index]
    except (IndexError, ValueError):
        await callback.answer()
        return
    await state.update_data(file_name=chosen)
    await callback.answer()
    await send_edited(callback.bot, chat_id_of(callback), state, session, db_user, lang, keep=True)


@router.callback_query(Flow.edit_menu, F.data == "file:download")
async def download_icon(callback: CallbackQuery, state: FSMContext, db_user: User, lang: str | None) -> None:
    await callback.answer()
    data = await state.get_data()
    chat_id = chat_id_of(callback)
    path = thumb_file(db_user.telegram_id)
    if data.get("thumb") and path.exists():
        await callback.bot.send_photo(chat_id, BufferedInputFile(path.read_bytes(), filename="icon.jpg"))
        return
    thumb_id = str(data.get("thumb_id") or "")
    if thumb_id:
        await callback.bot.send_photo(chat_id, thumb_id)
        return
    await callback.bot.send_message(chat_id, t(lang, "no_icon"), reply_markup=file_drop_kb(lang))


@router.callback_query(Flow.edit_menu, F.data == "file:delete")
async def delete_icon(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None
) -> None:
    delete_thumb(db_user.telegram_id)
    await state.update_data(thumb=False, clear_icon=True)
    await callback.answer()
    await send_edited(callback.bot, chat_id_of(callback), state, session, db_user, lang, keep=True)


@router.callback_query(Flow.edit_menu, F.data.in_({"edit:name", "file:rename"}))
async def ask_name(callback: CallbackQuery, state: FSMContext, lang: str | None) -> None:
    data = await state.get_data()
    await state.set_state(Flow.edit_name)
    await callback.answer()
    await callback.bot.send_message(
        chat_id_of(callback),
        t(lang, "ask_new_name", name=escape(str(data.get("file_name") or "fayl"))),
    )


@router.message(Flow.edit_name, F.text)
async def set_name(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    data = await state.get_data()
    ext = str(data.get("ext") or Path(str(data.get("file_name") or "")).suffix)
    new_name = safe_filename(message.text or "", ext)
    await state.update_data(file_name=new_name)
    await state.set_state(Flow.edit_menu)
    if data.get("from_drop"):
        await send_edited(message.bot, message.chat.id, state, session, db_user, lang, keep=True)
        return
    await message.answer(
        t(lang, "name_set", name=escape(new_name)),
        reply_markup=edit_kb(lang, is_premium(db_user)),
    )


@router.callback_query(Flow.edit_menu, F.data == "edit:thumb")
async def ask_thumb(callback: CallbackQuery, state: FSMContext, db_user: User, lang: str | None) -> None:
    if not is_premium(db_user):
        await callback.answer(t(lang, "thumb_premium"), show_alert=True)
        await callback.bot.send_message(chat_id_of(callback), t(lang, "thumb_premium"), reply_markup=premium_kb(lang))
        return
    await state.set_state(Flow.edit_thumb)
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_thumb"))


@router.message(Flow.edit_thumb, F.photo | F.document)
async def set_thumb(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    data = await state.get_data()
    if not is_premium(db_user) and not data.get("from_drop"):
        await state.set_state(Flow.edit_menu)
        await message.answer(t(lang, "thumb_premium"), reply_markup=premium_kb(lang))
        return
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer(t(lang, "thumb_bad"))
        return
    try:
        tg_file = await message.bot.get_file(file_id)
        buffer = io.BytesIO()
        await message.bot.download_file(tg_file.file_path, destination=buffer)
        blob = make_thumbnail(buffer.getvalue())
    except (TelegramBadRequest, OSError, UserFacingError):
        await message.answer(t(lang, "thumb_bad"))
        return
    if magic_kind_bytes(blob) != "jpg":
        await message.answer(t(lang, "thumb_bad"))
        return
    path = thumb_file(db_user.telegram_id)
    path.write_bytes(blob)
    await state.update_data(thumb=True, clear_icon=False)
    await state.set_state(Flow.edit_menu)
    if data.get("from_drop"):
        await send_edited(message.bot, message.chat.id, state, session, db_user, lang, keep=True)
        return
    await message.answer(t(lang, "thumb_set"), reply_markup=edit_kb(lang, True))


def magic_kind_bytes(blob: bytes) -> str:
    if blob[:3] == b"\xff\xd8\xff":
        return "jpg"
    return "other"


@router.callback_query(Flow.edit_menu, F.data == "edit:done")
async def edit_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    await callback.answer()
    await send_edited(callback.bot, chat_id_of(callback), state, session, db_user, lang)


async def send_edited(
    bot, chat_id: int, state: FSMContext, session: AsyncSession, user: User, lang: str | None, *, keep: bool = False
) -> None:
    data = await state.get_data()
    info = stored_info(data)
    if not info.get("file_id"):
        await bot.send_message(chat_id, t(lang, "ask_any_file"))
        return
    if not is_premium(user):
        used = await today_count(session, user.id)
        if used >= settings.free_daily_limit:
            await bot.send_message(chat_id, t(lang, "limit_reached", limit=settings.free_daily_limit), reply_markup=premium_kb(lang))
            return
    if not await busy.try_enter(user.telegram_id):
        await bot.send_message(chat_id, t(lang, "busy"))
        return
    folder = settings.temp_dir / "jobs" / f"edit_{user.telegram_id}_{uuid.uuid4().hex}"
    status = None
    try:
        status = await bot.send_message(chat_id, t(lang, "working"))
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "fayl"
        await _download(bot, info, dest, None, settings.premium_max_mb * 1024 * 1024 if is_premium(user) else settings.free_max_mb * 1024 * 1024)
        filename = safe_filename(str(data.get("file_name") or "fayl"), str(data.get("ext") or ""))
        # safe_filename qayta kengaytma qo'shmasligi uchun nom allaqachon to'liq bo'lsa ham tekshiramiz.
        if data.get("ext") and not filename.lower().endswith(str(data["ext"]).lower()):
            filename = safe_filename(Path(filename).stem, str(data["ext"]))
        used = await today_count(session, user.id)
        left = None if is_premium(user) else settings.free_daily_limit - used - 1
        thumb = None
        thumb_path = thumb_file(user.telegram_id)
        if data.get("clear_icon"):
            thumb = BufferedInputFile(blank_thumbnail(), filename="thumb.jpg")
        elif data.get("thumb") and thumb_path.exists() and (is_premium(user) or data.get("from_drop")):
            thumb = BufferedInputFile(thumb_path.read_bytes(), filename="thumb.jpg")
        markup = file_drop_kb(lang) if keep and data.get("from_drop") else None
        if markup is None and left is not None and left <= 0:
            markup = premium_kb(lang)
        await bot.send_document(
            chat_id,
            BufferedInputFile(dest.read_bytes(), filename=filename),
            caption=t(lang, "result_caption", filename=escape(filename), limit_line=limit_line(lang, left)),
            thumbnail=thumb,
            reply_markup=markup,
        )
        await add_usage(session, user.id, "rename")
        if keep:
            await state.set_state(Flow.edit_menu)
        else:
            await state.clear()
            delete_thumb(user.telegram_id)
    except UserFacingError as exc:
        await bot.send_message(
            chat_id,
            t(lang, exc.key, **exc.params),
            reply_markup=file_drop_kb(lang) if data.get("from_drop") else None,
        )
    except Exception:
        logger.exception("Nom yoki rasm yuborilmadi")
        await bot.send_message(
            chat_id,
            t(lang, "error_generic"),
            reply_markup=file_drop_kb(lang) if data.get("from_drop") else None,
        )
    finally:
        await busy.leave(user.telegram_id)
        if status is not None:
            try:
                await bot.delete_message(chat_id, status.message_id)
            except Exception:
                pass
        import shutil

        shutil.rmtree(folder, ignore_errors=True)


@router.message(Flow.edit_menu)
async def edit_hint(message: Message, state: FSMContext, db_user: User, lang: str | None) -> None:
    data = await state.get_data()
    if data.get("from_drop"):
        await message.answer(
            t(lang, "file_ready", name=escape(str(data.get("file_name") or "fayl"))),
            reply_markup=file_drop_kb(lang),
        )
        return
    await message.answer(t(lang, "edit_wait"), reply_markup=edit_kb(lang, is_premium(db_user)))


@router.message(Flow.edit_thumb)
async def thumb_hint(message: Message, lang: str | None) -> None:
    await message.answer(t(lang, "ask_thumb"))
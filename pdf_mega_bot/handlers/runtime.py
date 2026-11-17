"""Faylni yuklab olish, ishni 60 soniya ichida bajarish va natijani yuborish."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from html import escape
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_DIR, settings
from database.crud import add_usage, today_count
from database.models import User
from keyboards.common import angle_kb, cancel_kb, collect_kb, edit_kb, premium_kb
from services.errors import UserFacingError
from services.files import (
    IMAGE_KINDS,
    WORD_KINDS,
    classify,
    delete_thumb,
    human_size,
    magic_kind,
)
from services.i18n import t
from services.limits import is_premium, max_bytes_for, max_mb_for
from services.pdf_service import page_count
from services.queue import BusySet, WorkQueue
from states.states import CONVERT_ACTIONS, PROMPTS, TOOL_ACTIONS, Flow

logger = logging.getLogger(__name__)
router = Router()
busy = BusySet()
work_queue = WorkQueue(settings.queue_slots)

FILE_KEYS = ("file_id", "file_name", "file_size", "kind")


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def info_from_message(message: Message) -> dict | None:
    if message.photo:
        photo = message.photo[-1]
        return {
            "file_id": photo.file_id,
            "file_name": "rasm.jpg",
            "file_size": photo.file_size or 0,
            "kind": "jpg",
            "thumb_id": "",
        }
    document = message.document
    if document is None:
        return None
    name = document.file_name
    mime = document.mime_type or ""
    if not name:
        ext = {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
        }.get(mime, "")
        name = f"fayl{ext}"
    thumb = document.thumbnail
    return {
        "file_id": document.file_id,
        "file_name": name,
        "file_size": document.file_size or 0,
        "kind": classify(name, mime) or "other",
        "thumb_id": thumb.file_id if thumb is not None else "",
    }


def stored_info(data: dict) -> dict:
    return {key: data.get(key) for key in FILE_KEYS}


def chat_id_of(event: Message | CallbackQuery) -> int:
    if isinstance(event, Message):
        return event.chat.id
    if event.message is not None and getattr(event.message, "chat", None) is not None:
        return event.message.chat.id
    return event.from_user.id


def limit_line(lang: str | None, left: int | None) -> str:
    if left is None:
        return t(lang, "limit_unlimited")
    if left <= 0:
        return t(lang, "limit_last")
    return t(lang, "limit_left", left=left)


async def ask_for(bot: Bot, chat_id: int, state: FSMContext, lang: str | None, action: str) -> None:
    await state.clear()
    if action == "img2pdf":
        await state.set_state(Flow.collect_images)
        await state.update_data(files=[])
        await bot.send_message(
            chat_id,
            t(lang, "ask_images"),
            reply_markup=collect_kb(lang, 0, "collect:images", "act_done_count"),
        )
        return
    if action == "merge":
        await state.set_state(Flow.collect_merge)
        await state.update_data(files=[])
        await bot.send_message(
            chat_id,
            t(lang, "ask_merge"),
            reply_markup=collect_kb(lang, 0, "collect:merge", "act_merge_go_count"),
        )
        return
    await state.set_state(Flow.wait_file)
    await state.update_data(action=action)
    await bot.send_message(chat_id, t(lang, PROMPTS.get(action, "ask_pdf")), reply_markup=cancel_kb(lang))


async def _download(bot: Bot, info: dict, dest: Path, expected: set[str] | None, max_bytes: int) -> None:
    size = int(info.get("file_size") or 0)
    if size and size > max_bytes:
        raise UserFacingError("file_too_big", max_mb=max_bytes // (1024 * 1024))
    try:
        tg_file = await bot.get_file(info["file_id"])
        await bot.download_file(tg_file.file_path, destination=dest, timeout=120)
    except TelegramBadRequest as exc:
        if "too big" in str(exc).lower():
            raise UserFacingError("file_too_big", max_mb=max_bytes // (1024 * 1024)) from exc
        raise
    if dest.stat().st_size == 0:
        raise UserFacingError("bad_file")
    if dest.stat().st_size > max_bytes:
        raise UserFacingError("file_too_big", max_mb=max_bytes // (1024 * 1024))
    if expected is not None and magic_kind(dest) not in expected:
        raise UserFacingError("bad_file")


def _expected(action: str) -> set[str] | None:
    if action == "word2pdf":
        return set(WORD_KINDS)
    if action == "img2pdf":
        return set(IMAGE_KINDS)
    if action == "rename":
        return None
    return {"pdf"}


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


async def _run_worker(payload: dict, result_path: Path) -> dict:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "services.worker",
        str(result_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(BASE_DIR),
        start_new_session=True,
    )
    raw = json.dumps(payload).encode("utf-8")
    try:
        _stdout, stderr = await asyncio.wait_for(process.communicate(raw), timeout=settings.convert_timeout + 5)
    except TimeoutError:
        if process.pid:
            _kill_group(process.pid)
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            pass
        raise UserFacingError("timeout")
    if stderr:
        logger.info("Ish jurnali: %s", stderr.decode(errors="replace")[-800:])
    if not result_path.exists():
        raise UserFacingError("error_generic")
    return json.loads(result_path.read_text(encoding="utf-8"))


async def run_job(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    user: User,
    lang: str | None,
    action: str,
    files: list[dict],
    pages: list[int] | None = None,
    angle: int | None = None,
    usage_action: str | None = None,
) -> None:
    if not is_premium(user):
        used = await today_count(session, user.id)
        if used >= settings.free_daily_limit:
            await bot.send_message(
                chat_id,
                t(lang, "limit_reached", limit=settings.free_daily_limit),
                reply_markup=premium_kb(lang),
            )
            return
    if not await busy.try_enter(user.telegram_id):
        await bot.send_message(chat_id, t(lang, "busy"))
        return

    status = None
    folder = settings.temp_dir / "jobs" / f"{user.telegram_id}_{uuid.uuid4().hex}"
    try:
        status = await bot.send_message(chat_id, t(lang, "working"))
        folder.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        expected = _expected(action)
        limit = max_bytes_for(user)
        for index, info in enumerate(files):
            suffix = Path(str(info.get("file_name") or "")).suffix
            dest = folder / f"kirish_{index}{suffix}"
            await _download(bot, info, dest, expected, limit)
            paths.append(dest)
        payload = {
            "action": action,
            "inputs": [str(path) for path in paths],
            "out_dir": str(folder),
            "original_name": files[0].get("file_name") or "fayl",
            "pages": pages,
            "angle": angle,
            "watermark": not is_premium(user),
        }
        logger.info("Amal: user=%s action=%s files=%s", user.telegram_id, action, len(files))
        async with work_queue.slot(is_premium(user)):
            result = await _run_worker(payload, folder / "natija.json")
        if not result.get("ok"):
            params = result.get("params") or {}
            raise UserFacingError(str(result.get("error") or "error_generic"), **params)
        out_path = folder / str(result["stored_name"])
        filename = str(result["filename"])
        used = await today_count(session, user.id)
        left = None if is_premium(user) else settings.free_daily_limit - used - 1
        line = limit_line(lang, left)
        if action == "compress":
            caption = t(
                lang,
                "compress_caption",
                before=human_size(int(result.get("before") or 0)),
                after=human_size(int(result.get("after") or out_path.stat().st_size)),
                limit_line=line,
            )
        else:
            caption = t(lang, "result_caption", filename=esc(filename), limit_line=line)
        markup = premium_kb(lang) if left is not None and left <= 0 else None
        await bot.send_document(
            chat_id,
            BufferedInputFile(out_path.read_bytes(), filename=filename),
            caption=caption,
            reply_markup=markup,
        )
        await add_usage(session, user.id, usage_action or action)
    except UserFacingError as exc:
        await bot.send_message(chat_id, t(lang, exc.key, **exc.params))
    except Exception:
        logger.exception("Amal bajarilmadi: %s", action)
        await bot.send_message(chat_id, t(lang, "error_generic"))
    finally:
        await busy.leave(user.telegram_id)
        if status is not None:
            try:
                await bot.delete_message(chat_id, status.message_id)
            except Exception:
                pass
        # Fayl mazmuni saqlanmaydi.
        import shutil

        shutil.rmtree(folder, ignore_errors=True)


async def peek_pages(bot: Bot, info: dict, user: User) -> int:
    folder = settings.temp_dir / "jobs" / f"peek_{user.telegram_id}_{uuid.uuid4().hex}"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "peek.pdf"
    try:
        await _download(bot, info, dest, {"pdf"}, max_bytes_for(user))
        return page_count(dest)
    finally:
        import shutil

        shutil.rmtree(folder, ignore_errors=True)


def _kind_ok(action: str, kind: str) -> str | None:
    if action in PDF_ACTIONS and kind != "pdf":
        return "ask_pdf"
    if action == "word2pdf" and kind not in WORD_KINDS:
        return "ask_word"
    if action == "img2pdf" and kind not in IMAGE_KINDS:
        return "ask_images"
    return None


PDF_ACTIONS = {"pdf2word", "pdf2img", "compress", "split", "delete", "rotate", "merge"}


async def take_file(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    lang: str | None,
    action: str,
    info: dict,
) -> None:
    size = int(info.get("file_size") or 0)
    if size and size > max_bytes_for(user):
        await bot.send_message(chat_id, t(lang, "file_too_big", max_mb=max_mb_for(user)))
        return
    problem = _kind_ok(action, str(info.get("kind")))
    if problem and action != "edit":
        await bot.send_message(chat_id, t(lang, problem))
        return

    if action in {"pdf2word", "word2pdf", "pdf2img", "compress"}:
        await state.clear()
        await run_job(bot, chat_id, session, user, lang, action, [info])
        return

    if action == "img2pdf":
        await state.set_state(Flow.collect_images)
        await state.update_data(files=[info])
        await bot.send_message(
            chat_id,
            t(lang, "added_file", count=1),
            reply_markup=collect_kb(lang, 1, "collect:images", "act_done_count"),
        )
        return

    if action == "merge":
        files = [info] if info.get("kind") == "pdf" else []
        await state.set_state(Flow.collect_merge)
        await state.update_data(files=files)
        if not files:
            await bot.send_message(chat_id, t(lang, "ask_merge"), reply_markup=cancel_kb(lang))
            return
        await bot.send_message(
            chat_id,
            t(lang, "added_file", count=1),
            reply_markup=collect_kb(lang, 1, "collect:merge", "act_merge_go_count"),
        )
        return

    if action in {"split", "delete"}:
        await state.set_state(Flow.wait_pages)
        await state.update_data(action=action, **info)
        key = "ask_pages_split" if action == "split" else "ask_pages_delete"
        await bot.send_message(chat_id, t(lang, key), reply_markup=cancel_kb(lang))
        return

    if action == "rotate":
        await state.set_state(Flow.wait_angle)
        await state.update_data(action="rotate", **info)
        await bot.send_message(chat_id, t(lang, "ask_angle"), reply_markup=angle_kb(lang))
        return

    if action == "edit":
        ext = Path(str(info.get("file_name") or "")).suffix
        delete_thumb(user.telegram_id)
        await state.set_state(Flow.edit_menu)
        await state.update_data(ext=ext, thumb=False, **info)
        await bot.send_message(
            chat_id,
            t(lang, "edit_intro", name=esc(info.get("file_name") or "fayl")),
            reply_markup=edit_kb(lang, is_premium(user)),
        )


async def append_collected(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    user: User,
    lang: str | None,
    info: dict,
    *,
    images: bool,
) -> None:
    size = int(info.get("file_size") or 0)
    if size and size > max_bytes_for(user):
        await bot.send_message(chat_id, t(lang, "file_too_big", max_mb=max_mb_for(user)))
        return
    if images and info.get("kind") not in IMAGE_KINDS:
        await bot.send_message(chat_id, t(lang, "ask_images"))
        return
    if not images and info.get("kind") != "pdf":
        await bot.send_message(chat_id, t(lang, "ask_merge"))
        return
    data = await state.get_data()
    files = list(data.get("files") or [])
    maximum = settings.max_images if images else settings.max_merge_files
    if len(files) >= maximum:
        await bot.send_message(chat_id, t(lang, "too_many_files", max=maximum))
        return
    files.append(info)
    await state.update_data(files=files)
    label = "act_done_count" if images else "act_merge_go_count"
    callback = "collect:images" if images else "collect:merge"
    await bot.send_message(
        chat_id,
        t(lang, "added_file", count=len(files)),
        reply_markup=collect_kb(lang, len(files), callback, label),
    )


@router.message(Flow.wait_file, F.photo | F.document)
async def on_wait_file(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    info = info_from_message(message)
    if info is None:
        return
    action = (await state.get_data()).get("action")
    if action not in CONVERT_ACTIONS | TOOL_ACTIONS | {"edit"}:
        await message.answer(t(lang, "unknown"))
        return
    await take_file(message.bot, message.chat.id, state, session, db_user, lang, str(action), info)


@router.message(Flow.wait_file)
async def remind_wait_file(message: Message, state: FSMContext, lang: str | None) -> None:
    action = (await state.get_data()).get("action")
    await message.answer(t(lang, PROMPTS.get(str(action), "ask_pdf")), reply_markup=cancel_kb(lang))

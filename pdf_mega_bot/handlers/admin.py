"""Telegram ichidagi admin: statistika, to'lov, premium va xabar."""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import (
    get_or_create_id,
    get_payment,
    grant_premium,
    is_admin,
    list_telegram_ids,
    pending_payments,
    revoke_premium,
    stats,
    sync_admins,
)
from database.models import User
from handlers.runtime import chat_id_of
from keyboards.common import admin_kb, confirm_kb
from services.i18n import t
from services.payments import format_som, plan_title
from services.timeutil import format_dt, utcnow
from states.states import ACTION_LABELS, Flow

logger = logging.getLogger(__name__)
router = Router()


def _username(event: Message | CallbackQuery) -> str:
    return (event.from_user.username or "").lower()


async def ensure_admin(event: Message | CallbackQuery, session: AsyncSession, lang: str | None) -> bool:
    user_id = event.from_user.id
    by_name = _username(event) in settings.admin_usernames
    allowed = by_name or user_id in settings.admin_ids or await is_admin(session, user_id)
    if allowed:
        if by_name:
            await sync_admins(session, (user_id,))
        return True
    if isinstance(event, CallbackQuery):
        await event.answer(t(lang, "not_admin"), show_alert=True)
    else:
        await event.answer(t(lang, "not_admin"))
    return False


async def reset_admin(state: FSMContext) -> None:
    await state.clear()


@router.message(Command("admin", "panel"))
async def cmd_admin(message: Message, state: FSMContext, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(message, session, lang):
        return
    await reset_admin(state)
    await message.answer(t(lang, "admin_title"), reply_markup=admin_kb(lang))


@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    data = await stats(session)
    lines = []
    for action, count in data["top"]:
        lines.append(f"• {t(lang, ACTION_LABELS.get(action, 'unknown'))}: {count}")
    top = "\n".join(lines) if lines else "—"
    await callback.answer()
    await callback.bot.send_message(
        chat_id_of(callback),
        t(
            lang,
            "admin_stats",
            total=data["total"],
            new=data["new"],
            active=data["active"],
            premium=data["premium"],
            stars=data["stars"],
            card=format_som(data["card"]),
            top=top,
        ),
    )


@router.callback_query(F.data == "admin:pending")
async def show_pending(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    rows = await pending_payments(session)
    await callback.answer()
    if not rows:
        await callback.bot.send_message(chat_id_of(callback), t(lang, "no_pending"))
        return
    from keyboards.common import pay_kb

    for payment, user in rows:
        who = f"@{escape(user.username)}" if user.username else str(user.telegram_id)
        caption = t(
            lang,
            "payment_caption",
            id=payment.id,
            user=who,
            tid=user.telegram_id,
            plan=plan_title(lang, payment.plan_days),
            amount=format_som(payment.amount) if payment.method == "card" else str(payment.amount),
            method=t(lang, "method_card" if payment.method == "card" else "method_stars"),
        )
        markup = pay_kb(payment.id, lang)
        if payment.receipt_file_id:
            try:
                await callback.bot.send_photo(chat_id_of(callback), payment.receipt_file_id, caption=caption, reply_markup=markup)
                continue
            except Exception:
                logger.info("Chek rasmi ochilmadi: %s", payment.id)
        await callback.bot.send_message(chat_id_of(callback), caption, reply_markup=markup)


@router.callback_query(F.data.startswith("pay:ok:"))
async def approve(callback: CallbackQuery, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    payment_id = int((callback.data or "").rsplit(":", 1)[1])
    found = await get_payment(session, payment_id)
    if found is None:
        await callback.answer(t(lang, "no_pending"), show_alert=True)
        return
    payment, user = found
    if payment.status != "pending":
        await callback.answer(t(lang, "payment_done"), show_alert=True)
        return
    until = await grant_premium(session, user, payment.plan_days)
    payment.status = "approved"
    payment.approved_at = utcnow()
    await session.commit()
    await callback.answer(t(lang, "payment_done"))
    try:
        await callback.bot.send_message(
            user.telegram_id,
            t(user.language, "payment_approved", days=payment.plan_days, until=format_dt(until)),
        )
    except Exception:
        logger.exception("Foydalanuvchiga tasdiq yuborilmadi: %s", user.telegram_id)


@router.callback_query(F.data.startswith("pay:no:"))
async def ask_reject(callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    payment_id = int((callback.data or "").rsplit(":", 1)[1])
    found = await get_payment(session, payment_id)
    if found is None or found[0].status != "pending":
        await callback.answer(t(lang, "payment_done"), show_alert=True)
        return
    await state.set_state(Flow.admin_text)
    await state.update_data(purpose="reject", payment_id=payment_id)
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_reject_reason"))


@router.callback_query(F.data == "admin:grant")
async def ask_grant(callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    await state.set_state(Flow.admin_text)
    await state.update_data(purpose="grant_id")
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_grant_id"))


@router.callback_query(F.data == "admin:revoke")
async def ask_revoke(callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str) -> None:
    if not await ensure_admin(callback, session, lang):
        return
    await state.set_state(Flow.admin_text)
    await state.update_data(purpose="revoke_id")
    await callback.answer()
    await callback.bot.send_message(chat_id_of(callback), t(lang, "ask_revoke_id"))


@router.callback_query(F.data.startswith("bc:"))
async def broadcast_audience(callback: CallbackQuery, state: FSMContext, session: AsyncSession, lang: str) -> None:
    action = (callback.data or "").split(":", 1)[1]
    if action not in {"all", "premium", "free", "yes", "no"}:
        return
    if not await ensure_admin(callback, session, lang):
        return
    await callback.answer()
    if action == "no":
        await state.clear()
        await callback.bot.send_message(chat_id_of(callback), t(lang, "cancelled"), reply_markup=admin_kb(lang))
        return
    if action == "yes":
        data = await state.get_data()
        text = str(data.get("broadcast_text") or "")
        audience = str(data.get("audience") or "all")
        await state.clear()
        if not text:
            await callback.bot.send_message(chat_id_of(callback), t(lang, "broadcast_empty"))
            return
        ids = await list_telegram_ids(session, audience)
        await session.commit()
        sent, failed = await _broadcast(callback.bot, ids, text)
        await callback.bot.send_message(
            chat_id_of(callback),
            t(lang, "broadcast_done", sent=sent, failed=failed),
            reply_markup=admin_kb(lang),
        )
        return
    await state.set_state(Flow.admin_text)
    await state.update_data(purpose="broadcast", audience=action)
    await callback.bot.send_message(
        chat_id_of(callback),
        t(lang, "ask_broadcast", audience=t(lang, f"audience_{action}")),
    )


async def _broadcast(bot, ids: list[int], text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for telegram_id in ids:
        try:
            await bot.send_message(telegram_id, escape(text))
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(telegram_id, escape(text))
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    return sent, failed


@router.message(Flow.admin_text, F.text)
async def admin_text(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str) -> None:
    if not await ensure_admin(message, session, lang):
        await state.clear()
        return
    data = await state.get_data()
    purpose = data.get("purpose")
    text = (message.text or "").strip()
    if purpose == "reject":
        if len(text) > 500:
            await message.answer(t(lang, "text_too_long"))
            return
        found = await get_payment(session, int(data.get("payment_id") or 0))
        await state.clear()
        if found is None or found[0].status != "pending":
            await message.answer(t(lang, "payment_done"))
            return
        payment, user = found
        payment.status = "rejected"
        payment.reject_reason = text
        await session.commit()
        await message.answer(t(lang, "payment_done"), reply_markup=admin_kb(lang))
        try:
            await message.bot.send_message(user.telegram_id, t(user.language, "payment_rejected", reason=escape(text)))
        except Exception:
            logger.exception("Rad xabari yuborilmadi: %s", user.telegram_id)
        return
    if purpose == "grant_id":
        if not text.isdigit():
            await message.answer(t(lang, "bad_number"))
            return
        await state.update_data(purpose="grant_days", target_id=int(text))
        await message.answer(t(lang, "ask_grant_days"))
        return
    if purpose == "grant_days":
        if not text.isdigit() or not (1 <= int(text) <= 3650):
            await message.answer(t(lang, "bad_number"))
            return
        days = int(text)
        target_id = int(data.get("target_id") or 0)
        if target_id <= 0:
            await message.answer(t(lang, "bad_number"))
            return
        target = await get_or_create_id(session, target_id)
        until = await grant_premium(session, target, days)
        await session.commit()
        await state.clear()
        notice = t(target.language, "grant_notice", days=days, until=format_dt(until))
        try:
            await message.bot.send_message(target.telegram_id, notice)
            await message.answer(t(lang, "grant_ok", user_id=target.telegram_id, days=days), reply_markup=admin_kb(lang))
        except Exception:
            await message.answer(t(lang, "grant_ok_no_dm", user_id=target.telegram_id, days=days), reply_markup=admin_kb(lang))
        return
    if purpose == "revoke_id":
        if not text.isdigit():
            await message.answer(t(lang, "bad_number"))
            return
        target = await get_or_create_id(session, int(text))
        await revoke_premium(session, target)
        await session.commit()
        await state.clear()
        await message.answer(t(lang, "revoke_ok", user_id=target.telegram_id), reply_markup=admin_kb(lang))
        try:
            await message.bot.send_message(target.telegram_id, t(target.language, "revoke_notice"))
        except Exception:
            logger.info("Premium olindi, foydalanuvchi botni ochmagan: %s", target.telegram_id)
        return
    if purpose == "broadcast":
        if not text:
            await message.answer(t(lang, "broadcast_empty"))
            return
        if len(text) > 3500:
            await message.answer(t(lang, "text_too_long"))
            return
        await state.update_data(broadcast_text=text)
        await message.answer(t(lang, "broadcast_confirm", text=escape(text)), reply_markup=confirm_kb(lang))
        return
    await state.clear()
    await message.answer(t(lang, "unknown"))

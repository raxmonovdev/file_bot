"""Premium: Telegram Stars yoki karta cheki."""

from __future__ import annotations

import logging
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import add_payment, admin_ids, grant_premium, payment_by_external
from database.models import User
from handlers.runtime import chat_id_of
from keyboards.common import pay_kb
from services.i18n import t
from services.payments import find_plan, format_som, make_payload, parse_payload, plan_title
from services.timeutil import format_dt, utcnow
from states.states import Flow

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("buy:"))
async def buy(callback: CallbackQuery, state: FSMContext, db_user: User, lang: str | None) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _prefix, method, days_raw = parts
    try:
        days = int(days_raw)
    except ValueError:
        await callback.answer()
        return
    plan = find_plan(days)
    if plan is None or method not in {"stars", "card"}:
        await callback.answer()
        return
    await callback.answer()
    title = plan_title(lang, plan.days)
    if method == "stars":
        await callback.bot.send_invoice(
            chat_id_of(callback),
            title=t(lang, "invoice_title", plan=title),
            description=t(lang, "invoice_desc", plan=title),
            payload=make_payload(plan.days, db_user.telegram_id),
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=plan.stars)],
            provider_token="",
        )
        return
    if not settings.card_number:
        await callback.bot.send_message(chat_id_of(callback), t(lang, "card_missing"))
        return
    await state.set_state(Flow.wait_receipt)
    await state.update_data(plan_days=plan.days, amount=plan.uzs)
    await callback.bot.send_message(
        chat_id_of(callback),
        t(
            lang,
            "card_info",
            plan=title,
            amount=format_som(plan.uzs),
            card=settings.card_number,
            holder=settings.card_holder or "—",
        ),
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    parsed = parse_payload(query.invoice_payload)
    if parsed is None or parsed[1] != query.from_user.id:
        await query.answer(ok=False, error_message="Payment payload is invalid")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def stars_paid(message: Message, session: AsyncSession, db_user: User, lang: str | None) -> None:
    payment = message.successful_payment
    if payment is None or payment.currency != "XTR":
        return
    parsed = parse_payload(payment.invoice_payload)
    if parsed is None or parsed[1] != message.from_user.id:
        return
    if await payment_by_external(session, payment.telegram_payment_charge_id):
        return
    plan, _telegram_id = parsed
    until = await grant_premium(session, db_user, plan.days)
    await add_payment(
        session,
        user_id=db_user.id,
        amount=payment.total_amount,
        method="stars",
        status="approved",
        plan_days=plan.days,
        external_id=payment.telegram_payment_charge_id,
        created_at=utcnow(),
        approved_at=utcnow(),
    )
    await message.answer(t(lang or "uz", "payment_approved", days=plan.days, until=format_dt(until)))


@router.message(Flow.wait_receipt, F.photo | F.document)
async def card_receipt(message: Message, state: FSMContext, session: AsyncSession, db_user: User, lang: str | None) -> None:
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer(t(lang, "receipt_bad"))
        return
    data = await state.get_data()
    days = int(data.get("plan_days") or 0)
    amount = int(data.get("amount") or 0)
    plan = find_plan(days)
    if plan is None:
        await state.clear()
        await message.answer(t(lang, "error_generic"))
        return
    payment = await add_payment(
        session,
        user_id=db_user.id,
        amount=amount,
        method="card",
        status="pending",
        plan_days=days,
        receipt_file_id=file_id,
        created_at=utcnow(),
    )
    await session.commit()
    await state.clear()
    await message.answer(t(lang, "receipt_sent"))
    who = f"@{escape(db_user.username)}" if db_user.username else str(db_user.telegram_id)
    caption = t(
        lang,
        "payment_caption",
        id=payment.id,
        user=who,
        tid=db_user.telegram_id,
        plan=plan_title(lang, days),
        amount=format_som(amount),
        method=t(lang, "method_card"),
    )
    ids = set(settings.admin_ids) | await admin_ids(session)
    for admin_id in ids:
        try:
            await message.bot.send_photo(
                admin_id,
                file_id,
                caption=caption,
                reply_markup=pay_kb(payment.id, "uz"),
            )
        except Exception:
            logger.exception("Adminga chek yuborilmadi: %s", admin_id)


@router.message(Flow.wait_receipt)
async def receipt_need_photo(message: Message, lang: str | None) -> None:
    await message.answer(t(lang, "receipt_bad"))

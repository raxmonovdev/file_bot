"""Tugmalar. Matnlar tanlangan tildan olinadi."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from services.i18n import t
from services.payments import format_som, plan_title
from config import settings


def main_kb(lang: str | None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_convert")), KeyboardButton(text=t(lang, "btn_edit"))],
            [KeyboardButton(text=t(lang, "btn_merge_split")), KeyboardButton(text=t(lang, "btn_compress"))],
            [KeyboardButton(text=t(lang, "btn_profile")), KeyboardButton(text=t(lang, "btn_premium"))],
            [KeyboardButton(text=t(lang, "btn_help"))],
        ],
        resize_keyboard=True,
    )


def language_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇿 O‘zbekcha", callback_data="lang:uz")
    builder.button(text="🇷🇺 Русский", callback_data="lang:ru")
    builder.button(text="🇬🇧 English", callback_data="lang:en")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "btn_cancel"), callback_data="flow:cancel")
    return builder.as_markup()


def _with_cancel(lang: str | None, builder: InlineKeyboardBuilder) -> InlineKeyboardMarkup:
    builder.row(InlineKeyboardButton(text=t(lang, "btn_cancel"), callback_data="flow:cancel"))
    return builder.as_markup()


def convert_menu_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for action in ("pdf2word", "word2pdf", "img2pdf", "pdf2img"):
        builder.button(text=t(lang, f"act_{action}"), callback_data=f"go:{action}")
    builder.adjust(1)
    return builder.as_markup()


def edit_menu_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "act_delete"), callback_data="go:delete")
    builder.button(text=t(lang, "act_rotate"), callback_data="go:rotate")
    builder.button(text=t(lang, "act_edit"), callback_data="go:edit")
    builder.adjust(1)
    return builder.as_markup()


def tools_menu_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "act_merge"), callback_data="go:merge")
    builder.button(text=t(lang, "act_split"), callback_data="go:split")
    builder.adjust(1)
    return builder.as_markup()


def file_drop_kb(lang: str | None) -> InlineKeyboardMarkup:
    """Fayl tushishi bilan chiqadigan tugmalar."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "btn_change_icon"), callback_data="file:icon")
    builder.button(text=t(lang, "btn_rename_file"), callback_data="file:rename")
    builder.button(text=t(lang, "btn_auto_names"), callback_data="file:auto")
    builder.button(text=t(lang, "btn_download_icon"), callback_data="file:download")
    builder.button(text=t(lang, "btn_delete_icon"), callback_data="file:delete")
    builder.adjust(1)
    return builder.as_markup()


def auto_names_kb(lang: str | None, names: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(names):
        label = name if len(name) <= 40 else name[:18] + "…" + name[-18:]
        builder.button(text=label, callback_data=f"file:pick:{index}")
    builder.button(text=t(lang, "btn_back_file"), callback_data="file:menu")
    builder.adjust(1)
    return builder.as_markup()


def file_actions_kb(lang: str | None, kind: str) -> InlineKeyboardMarkup:
    if kind == "pdf":
        actions = ["pdf2word", "pdf2img", "compress", "split", "delete", "rotate", "merge", "edit"]
    elif kind in {"doc", "docx"}:
        actions = ["word2pdf", "edit"]
    elif kind in {"jpg", "png"}:
        actions = ["img2pdf", "edit"]
    else:
        actions = ["edit"]
    builder = InlineKeyboardBuilder()
    for action in actions:
        label_key = "act_edit" if action == "edit" else f"act_{action}"
        builder.button(text=t(lang, label_key), callback_data=f"do:{action}")
    builder.adjust(1)
    return _with_cancel(lang, builder)


def collect_kb(lang: str | None, count: int, callback: str, label_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, label_key, count=count), callback_data=callback)
    return _with_cancel(lang, builder)


def angle_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for angle, key in ((90, "angle_90"), (180, "angle_180"), (270, "angle_270")):
        builder.button(text=t(lang, key), callback_data=f"angle:{angle}")
    builder.adjust(3)
    return _with_cancel(lang, builder)


def edit_kb(lang: str | None, premium: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "act_rename"), callback_data="edit:name")
    thumb = t(lang, "act_thumb")
    if not premium:
        thumb += " ⭐"
    builder.button(text=thumb, callback_data="edit:thumb")
    builder.button(text=t(lang, "act_done"), callback_data="edit:done")
    builder.adjust(1)
    return _with_cancel(lang, builder)


def premium_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in settings.plans:
        title = plan_title(lang, plan.days)
        builder.button(
            text=t(lang, "btn_stars", plan=title, stars=plan.stars),
            callback_data=f"buy:stars:{plan.days}",
        )
        builder.button(
            text=t(lang, "btn_card", plan=title, uzs=format_som(plan.uzs)),
            callback_data=f"buy:card:{plan.days}",
        )
    builder.adjust(1)
    return builder.as_markup()


def pay_kb(payment_id: int, lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "btn_yes"), callback_data=f"pay:ok:{payment_id}")
    builder.button(text=t(lang, "btn_no"), callback_data=f"pay:no:{payment_id}")
    builder.adjust(2)
    return builder.as_markup()


def admin_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "btn_stats"), callback_data="admin:stats")
    builder.button(text=t(lang, "btn_pending"), callback_data="admin:pending")
    builder.button(text=t(lang, "btn_grant"), callback_data="admin:grant")
    builder.button(text=t(lang, "btn_revoke"), callback_data="admin:revoke")
    builder.button(text=t(lang, "btn_bc_all"), callback_data="bc:all")
    builder.button(text=t(lang, "btn_bc_premium"), callback_data="bc:premium")
    builder.button(text=t(lang, "btn_bc_free"), callback_data="bc:free")
    builder.adjust(2)
    return builder.as_markup()


def confirm_kb(lang: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t(lang, "btn_yes"), callback_data="bc:yes")
    builder.button(text=t(lang, "btn_no"), callback_data="bc:no")
    builder.adjust(2)
    return builder.as_markup()

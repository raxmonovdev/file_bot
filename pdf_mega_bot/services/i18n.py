"""Matnlar locales/*.json da. Kod ichida faqat kalit ishlatiladi."""

from __future__ import annotations

import json
import re
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "locales"
_CACHE: dict[str, dict[str, str]] = {}

for _code in ("uz", "ru", "en"):
    _CACHE[_code] = json.loads((_DIR / f"{_code}.json").read_text(encoding="utf-8"))


def t(lang: str | None, key: str, **params: object) -> str:
    table = _CACHE.get(lang or "", _CACHE["uz"])
    text = table.get(key) or _CACHE["uz"].get(key) or key
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text


def without_emoji(text: str) -> str:
    """Eski tugma matni (emojisiz) ham ishlashi uchun."""
    return re.sub(r"^[^\w]+", "", text, flags=re.UNICODE).strip()


def cancel_texts() -> set[str]:
    texts: set[str] = set()
    for table in _CACHE.values():
        raw = table["btn_cancel"]
        texts.add(raw)
        texts.add(without_emoji(raw))
    return texts


def menu_text_to_key() -> dict[str, str]:
    keys = (
        "btn_convert",
        "btn_edit",
        "btn_merge_split",
        "btn_compress",
        "btn_profile",
        "btn_premium",
        "btn_help",
    )
    mapping: dict[str, str] = {}
    for table in _CACHE.values():
        for key in keys:
            mapping[table[key]] = key
            mapping.setdefault(without_emoji(table[key]), key)
    return mapping


def done_words() -> set[str]:
    words = {"tayyor", "done", "готово", "ok", "готов"}
    for table in _CACHE.values():
        for key in ("act_done", "act_merge_go"):
            words.add(table[key].lower())
            words.add(without_emoji(table[key]).lower())
    return words

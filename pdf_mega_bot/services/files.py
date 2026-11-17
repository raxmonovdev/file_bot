"""Fayl nomi, turi, thumbnail va vaqtinchalik papka."""

from __future__ import annotations

import io
import logging
import random
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

FORBIDDEN = set('/\\:*?"<>|')
IMAGE_KINDS = {"jpg", "png"}
WORD_KINDS = {"doc", "docx"}


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def classify(file_name: str, mime: str | None) -> str | None:
    ext = Path(file_name).suffix.lower()
    by_ext = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "doc",
        ".jpg": "jpg",
        ".jpeg": "jpg",
        ".png": "png",
    }.get(ext)
    if by_ext:
        return by_ext
    mime = (mime or "").lower()
    if "pdf" in mime:
        return "pdf"
    if mime == "image/jpeg":
        return "jpg"
    if mime == "image/png":
        return "png"
    if "wordprocessingml" in mime:
        return "docx"
    if mime in {"application/msword", "application/vnd.ms-word"}:
        return "doc"
    return None


def magic_kind(path: Path) -> str:
    head = path.read_bytes()[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "doc"
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile:
            return "other"
        if any(name.startswith("word/") for name in names):
            return "docx"
    return "other"


def safe_filename(name: str, ext: str) -> str:
    """Taqiqlangan belgilarni olib tashlaydi va kengaytmani o'zi qo'shadi."""
    if ext and not ext.startswith("."):
        ext = "." + ext
    base = (name or "").replace("\n", " ").replace("\r", " ").strip()
    if ext and base.lower().endswith(ext.lower()):
        base = base[: -len(ext)].strip()
    cleaned = "".join(ch for ch in base if ch not in FORBIDDEN and ord(ch) >= 32)
    cleaned = " ".join(cleaned.split()).strip(" .")
    limit = max(1, 100 - len(ext))
    cleaned = cleaned[:limit].strip(" .")
    if not cleaned:
        cleaned = "fayl"
    return cleaned + ext


def make_thumbnail(data: bytes) -> bytes:
    """Telegram talabi: JPEG, tomoni 320 px gacha, 200 KB dan kichik."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    side = 320
    quality = 80
    while True:
        copy = img.copy()
        copy.thumbnail((side, side))
        buf = io.BytesIO()
        copy.save(buf, format="JPEG", quality=quality, optimize=True)
        blob = buf.getvalue()
        if len(blob) <= 200 * 1024:
            return blob
        if quality > 30:
            quality -= 10
        elif side > 64:
            side = int(side * 0.75)
            quality = 55
        else:
            return blob


def blank_thumbnail() -> bytes:
    """Ikonkani o'chirish uchun deyarli bo'sh kichik JPEG."""
    img = Image.new("RGB", (8, 8), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=40)
    return buf.getvalue()


def auto_names(original: str, ext: str) -> list[str]:
    """Fayl uchun bir nechta tayyor nom."""
    now = datetime.now()
    stem = Path(original).stem or "File"
    raw = [
        f"{stem}_{now.strftime('%H%M')}",
        f"Document_{now.strftime('%d%m%Y')}",
        f"File_{random.randint(1000, 9999)}",
        f"Scan_{now.strftime('%H%M%S')}",
        f"Note_{random.randint(10, 99)}",
    ]
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        safe = safe_filename(item, ext)
        if safe.lower() in seen:
            continue
        seen.add(safe.lower())
        names.append(safe)
    return names


def thumb_file(user_id: int) -> Path:
    folder = settings.temp_dir / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{user_id}.jpg"


def delete_thumb(user_id: int) -> None:
    path = settings.temp_dir / "thumbs" / f"{user_id}.jpg"
    path.unlink(missing_ok=True)


def reset_temp() -> None:
    """Bot qayta ishga tushsa, yarim qolgan fayllar o'chiriladi."""
    for name in ("jobs", "thumbs"):
        folder = settings.temp_dir / name
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)


def zip_files(paths: list[Path], dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, arcname=path.name)

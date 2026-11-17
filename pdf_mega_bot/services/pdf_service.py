"""PDF amallari: birlashtirish, bo'lish, siqish, sahifa, rasm."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from config import settings
from services.errors import UserFacingError

logger = logging.getLogger(__name__)

DONE_PAGE_WORDS = {"all", "*", "hammasi", "все", "всестраницы", "barchasi"}


def parse_pages(text: str, total: int) -> list[int] | None:
    """'3-7' yoki '1,3,5' ni 0 dan boshlanadigan sahifa raqamlariga aylantiradi."""
    raw = text.strip().lower().replace(" ", "")
    if raw in DONE_PAGE_WORDS:
        return list(range(total))
    pages: set[int] = set()
    for part in raw.split(","):
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            if not left.isdigit() or not right.isdigit():
                return None
            start, end = int(left), int(right)
            if start > end:
                start, end = end, start
            if start < 1 or end > total:
                return None
            pages.update(range(start - 1, end))
        else:
            if not part.isdigit():
                return None
            number = int(part)
            if number < 1 or number > total:
                return None
            pages.add(number - 1)
    if not pages:
        return None
    return sorted(pages)


def open_pdf(path: Path) -> fitz.Document:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise UserFacingError("bad_pdf") from exc
    if doc.is_encrypted and doc.needs_pass:
        doc.close()
        raise UserFacingError("pdf_protected")
    if doc.page_count < 1:
        doc.close()
        raise UserFacingError("bad_pdf")
    return doc


def page_count(path: Path) -> int:
    doc = open_pdf(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def _save(doc: fitz.Document, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest, garbage=4, deflate=True, clean=True)


def merge_pdfs(paths: list[Path], dest: Path) -> None:
    out = fitz.open()
    try:
        for path in paths:
            doc = open_pdf(path)
            try:
                out.insert_pdf(doc)
            finally:
                doc.close()
        _save(out, dest)
    finally:
        out.close()


def split_pdf(src: Path, pages: list[int], dest: Path) -> None:
    doc = open_pdf(src)
    out = fitz.open()
    try:
        if any(i < 0 or i >= doc.page_count for i in pages):
            raise UserFacingError("bad_pages", total=doc.page_count)
        for index in pages:
            out.insert_pdf(doc, from_page=index, to_page=index)
        _save(out, dest)
    finally:
        out.close()
        doc.close()


def delete_pages(src: Path, pages: list[int], dest: Path) -> None:
    doc = open_pdf(src)
    try:
        if any(i < 0 or i >= doc.page_count for i in pages):
            raise UserFacingError("bad_pages", total=doc.page_count)
        if len(set(pages)) >= doc.page_count:
            raise UserFacingError("keep_one")
        for index in sorted(set(pages), reverse=True):
            doc.delete_page(index)
        _save(doc, dest)
    finally:
        doc.close()


def rotate_pages(src: Path, pages: list[int], angle: int, dest: Path) -> None:
    if angle not in {90, 180, 270}:
        raise UserFacingError("ask_angle")
    doc = open_pdf(src)
    try:
        if any(i < 0 or i >= doc.page_count for i in pages):
            raise UserFacingError("bad_pages", total=doc.page_count)
        for index in pages:
            page = doc[index]
            page.set_rotation((page.rotation + angle) % 360)
        _save(doc, dest)
    finally:
        doc.close()


def compress_pdf(src: Path, dest: Path) -> tuple[int, int]:
    before = src.stat().st_size
    doc = open_pdf(src)
    try:
        if hasattr(doc, "rewrite_images"):
            try:
                doc.rewrite_images(dpi_threshold=110, quality=50)
            except Exception:
                logger.info("Rasmni qayta siqib bo'lmadi, oddiy siqish ishlatiladi")
        _save(doc, dest)
    finally:
        doc.close()
    if dest.stat().st_size > before:
        shutil.copyfile(src, dest)
    return before, dest.stat().st_size


def images_to_pdf(paths: list[Path], dest: Path) -> None:
    frames: list[Image.Image] = []
    try:
        for path in paths:
            img = Image.open(path)
            if img.mode in {"RGBA", "P"}:
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.split()[-1])
                img.close()
                img = background
            else:
                img = img.convert("RGB")
            frames.append(img)
        if not frames:
            raise UserFacingError("need_one_image")
        dest.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(dest, save_all=True, append_images=frames[1:], format="PDF", resolution=150)
    finally:
        for frame in frames:
            frame.close()


def pdf_to_images(src: Path, folder: Path) -> list[Path]:
    doc = open_pdf(src)
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        if doc.page_count > settings.max_image_pages:
            raise UserFacingError("too_many_pages", max=settings.max_image_pages)
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            dest = folder / f"sahifa-{index:02d}.jpg"
            pix.save(dest)
            paths.append(dest)
    finally:
        doc.close()
    return paths


def stamp_pdf(path: Path, text: str) -> None:
    doc = open_pdf(path)
    try:
        for page in doc:
            rect = page.rect
            page.insert_text(
                fitz.Point(rect.x0 + 36, max(rect.y0 + 12, rect.y1 - 18)),
                text,
                fontsize=8,
                color=(0.45, 0.45, 0.45),
                overlay=True,
            )
        tmp = path.with_name(path.stem + "-stamp.pdf")
        _save(doc, tmp)
    finally:
        doc.close()
    tmp.replace(path)


def stamp_jpeg(path: Path, text: str) -> None:
    img = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.text((8, max(0, img.height - 16)), text, fill=(140, 140, 140))
    img.save(path, format="JPEG", quality=85)
    img.close()

"""Og'ir ish shu yerda bajariladi. Bot jarayoni faqat natijani kutadi."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.converter import pdf_to_docx, stamp_docx, word_to_pdf
from services.errors import UserFacingError
from services.files import safe_filename, zip_files
from services.pdf_service import (
    compress_pdf,
    delete_pages,
    images_to_pdf,
    merge_pdfs,
    pdf_to_images,
    rotate_pages,
    split_pdf,
    stamp_jpeg,
    stamp_pdf,
)
from config import settings


@dataclass
class Output:
    path: Path
    filename: str
    before: int | None = None
    after: int | None = None


def execute_sync(
    action: str,
    inputs: list[Path],
    out_dir: Path,
    original_name: str,
    pages: list[int] | None,
    angle: int | None,
    watermark: bool,
) -> Output:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = settings.watermark_text if watermark else None
    stem = Path(original_name).stem or "fayl"

    if action == "pdf2word":
        dest = out_dir / "natija.docx"
        pdf_to_docx(inputs[0], dest)
        if stamp:
            stamp_docx(dest, stamp)
        return Output(dest, safe_filename(stem, ".docx"))

    if action == "word2pdf":
        dest = out_dir / "natija.pdf"
        word_to_pdf(inputs[0], dest, out_dir)
        if stamp:
            stamp_pdf(dest, stamp)
        return Output(dest, safe_filename(stem, ".pdf"))

    if action == "img2pdf":
        dest = out_dir / "natija.pdf"
        images_to_pdf(inputs, dest)
        if stamp:
            stamp_pdf(dest, stamp)
        name = stem if len(inputs) == 1 else "rasmlar"
        return Output(dest, safe_filename(name, ".pdf"))

    if action == "pdf2img":
        folder = out_dir / "pages"
        images = pdf_to_images(inputs[0], folder)
        if stamp:
            for image in images:
                stamp_jpeg(image, stamp)
        if len(images) == 1:
            return Output(images[0], safe_filename(stem, ".jpg"))
        archive = out_dir / "sahifalar.zip"
        zip_files(images, archive)
        return Output(archive, safe_filename(f"{stem}_sahifalar", ".zip"))

    if action == "merge":
        dest = out_dir / "natija.pdf"
        merge_pdfs(inputs, dest)
        if stamp:
            stamp_pdf(dest, stamp)
        return Output(dest, safe_filename("birlashtirilgan", ".pdf"))

    if action == "split":
        dest = out_dir / "natija.pdf"
        split_pdf(inputs[0], pages or [], dest)
        if stamp:
            stamp_pdf(dest, stamp)
        return Output(dest, safe_filename(f"{stem}_sahifa", ".pdf"))

    if action == "compress":
        dest = out_dir / "natija.pdf"
        before, after = compress_pdf(inputs[0], dest)
        if stamp:
            stamp_pdf(dest, stamp)
            after = dest.stat().st_size
        return Output(dest, safe_filename(f"{stem}_kichik", ".pdf"), before, after)

    if action == "delete":
        dest = out_dir / "natija.pdf"
        delete_pages(inputs[0], pages or [], dest)
        if stamp:
            stamp_pdf(dest, stamp)
        return Output(dest, safe_filename(f"{stem}_tahrir", ".pdf"))

    if action == "rotate":
        dest = out_dir / "natija.pdf"
        rotate_pages(inputs[0], pages or [], angle or 90, dest)
        if stamp:
            stamp_pdf(dest, stamp)
        return Output(dest, safe_filename(f"{stem}_burilgan", ".pdf"))

    raise UserFacingError("error_generic")

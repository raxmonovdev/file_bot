"""PDF ↔ Word. Word → PDF uchun LibreOffice kerak."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

from config import settings
from services.errors import UserFacingError

logger = logging.getLogger(__name__)

_SOFFICE: str | None | bool = None


def find_soffice() -> str | None:
    global _SOFFICE
    if _SOFFICE is False:
        return None
    if isinstance(_SOFFICE, str):
        return _SOFFICE
    candidates = [
        settings.soffice_path,
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            _SOFFICE = candidate
            return candidate
    _SOFFICE = False
    return None


def pdf_to_docx(src: Path, dest: Path) -> None:
    from pdf2docx import Converter

    converter = Converter(str(src))
    try:
        converter.convert(str(dest))
    except Exception as exc:
        raise UserFacingError("bad_pdf") from exc
    finally:
        converter.close()
    if not dest.exists() or dest.stat().st_size == 0:
        raise UserFacingError("bad_pdf")


def word_to_pdf(src: Path, dest: Path, work_dir: Path) -> None:
    soffice = find_soffice()
    if not soffice:
        raise UserFacingError("libreoffice_missing")
    profile = work_dir / "lo-profile"
    profile.mkdir(parents=True, exist_ok=True)
    # Har bir ishga alohida profil, aks holda LibreOffice bir-birini to'sadi.
    command = [
        soffice,
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--norestore",
        f"-env:UserInstallation={profile.as_uri()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(work_dir),
        str(src),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=settings.convert_timeout,
            env={**os.environ, "SAL_NO_NATIVE_FILE_LOCK": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise UserFacingError("timeout") from exc
    produced = work_dir / f"{src.stem}.pdf"
    if completed.returncode != 0 or not produced.exists():
        logger.warning("LibreOffice xatosi: %s", completed.stderr.decode(errors="replace")[-500:])
        raise UserFacingError("bad_file")
    if produced.resolve() != dest.resolve():
        produced.replace(dest)


def stamp_docx(path: Path, text: str) -> None:
    try:
        document = Document(str(path))
        paragraph = document.add_paragraph(text)
        run = paragraph.runs[0]
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(140, 140, 140)
        document.save(str(path))
    except Exception:
        logger.exception("DOCX ga yozuv qo'yilmadi")

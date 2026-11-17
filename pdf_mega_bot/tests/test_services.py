"""Xizmatlar va bazani Telegram siz tekshirish."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.crud import add_usage, grant_premium, today_count, upsert_user  # noqa: E402
from database.db import init_db, make_engine  # noqa: E402
from services.converter import find_soffice, word_to_pdf  # noqa: E402
from services.errors import UserFacingError  # noqa: E402
from services.files import magic_kind, make_thumbnail, safe_filename  # noqa: E402
from services.i18n import _CACHE  # noqa: E402
from services.limits import is_premium  # noqa: E402
from services.pdf_service import (  # noqa: E402
    compress_pdf,
    delete_pages,
    images_to_pdf,
    merge_pdfs,
    page_count,
    parse_pages,
    pdf_to_images,
    rotate_pages,
    split_pdf,
    stamp_pdf,
)
from services.queue import WorkQueue  # noqa: E402
from services.runner import execute_sync  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def test_name_and_pages() -> None:
    check(safe_filename('hisobot:2026', '.pdf') == 'hisobot2026.pdf', 'nom tozalanmadi')
    check(safe_filename('hisobot.pdf', '.pdf') == 'hisobot.pdf', 'kengaytma ikki marta qo\'yildi')
    check(len(safe_filename('a' * 200, '.pdf')) <= 100, 'nom 100 dan uzun')
    check(parse_pages('3-7', 10) == [2, 3, 4, 5, 6], 'oralig')
    check(parse_pages('1,3,5', 5) == [0, 2, 4], 'royxat')
    check(parse_pages('hammasi', 3) == [0, 1, 2], 'hammasi')
    check(parse_pages('0', 3) is None, 'nol sahifa')
    check(parse_pages('8', 3) is None, 'chetki sahifa')


def test_thumbnail() -> None:
    image = Image.new('RGB', (800, 600), (20, 40, 200))
    folder = Path(tempfile.mkdtemp())
    src = folder / 'big.jpg'
    image.save(src, quality=95)
    blob = make_thumbnail(src.read_bytes())
    check(len(blob) <= 200 * 1024, 'thumbnail 200 KB dan katta')
    out = Image.open(__import__('io').BytesIO(blob))
    check(max(out.size) <= 320, 'thumbnail tomoni 320 dan katta')
    check(blob[:3] == b'\xff\xd8\xff', 'thumbnail JPEG emas')


def test_pdf_tools() -> None:
    folder = Path(tempfile.mkdtemp())
    src = folder / 'a.pdf'
    doc = fitz.open()
    for index in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f'Sahifa {index + 1}')
    doc.save(src)
    doc.close()
    check(page_count(src) == 3, 'sahifa soni')
    check(magic_kind(src) == 'pdf', 'magic pdf')

    part = folder / 'part.pdf'
    split_pdf(src, [1, 2], part)
    check(page_count(part) == 2, 'split')

    merged = folder / 'merged.pdf'
    merge_pdfs([src, src], merged)
    check(page_count(merged) == 6, 'merge')

    removed = folder / 'removed.pdf'
    delete_pages(src, [0], removed)
    check(page_count(removed) == 2, 'delete')
    try:
        delete_pages(src, [0, 1, 2], folder / 'no.pdf')
        raise SystemExit('hamma sahifa o\'chdi')
    except UserFacingError as exc:
        check(exc.key == 'keep_one', 'keep_one emas')

    rotated = folder / 'rot.pdf'
    rotate_pages(src, [0], 90, rotated)
    opened = fitz.open(rotated)
    check(opened[0].rotation == 90, 'rotate')
    opened.close()

    squeezed = folder / 'small.pdf'
    before, after = compress_pdf(src, squeezed)
    check(before > 0 and after > 0 and magic_kind(squeezed) == 'pdf', 'compress')
    stamp_pdf(squeezed, 'PDF Mega Bot')
    check(page_count(squeezed) == 3, 'stamp sahifa')

    picture = folder / 'pic.jpg'
    Image.new('RGB', (200, 100), 'white').save(picture)
    pdf_from_image = folder / 'img.pdf'
    images_to_pdf([picture, picture], pdf_from_image)
    check(page_count(pdf_from_image) == 2, 'rasm pdf')
    images = pdf_to_images(src, folder / 'pages')
    check(len(images) == 3 and images[0].exists(), 'pdf rasm')

    output = execute_sync('split', [src], folder / 'out', 'hujjat.pdf', [0], None, True)
    check(output.path.exists() and output.filename.endswith('.pdf'), 'runner split')


def test_word_converter() -> None:
    folder = Path(tempfile.mkdtemp())
    from docx import Document

    docx = folder / 'matn.docx'
    document = Document()
    document.add_paragraph('Salom')
    document.save(docx)
    dest = folder / 'natija.pdf'
    if find_soffice():
        word_to_pdf(docx, dest, folder)
        check(dest.exists() and magic_kind(dest) == 'pdf', 'word pdf')
    else:
        try:
            word_to_pdf(docx, dest, folder)
            raise SystemExit('LibreOffice yo\'q, lekin xato chiqmadi')
        except UserFacingError as exc:
            check(exc.key == 'libreoffice_missing', 'libreoffice xabari yo\'q')


def test_worker() -> None:
    folder = Path(tempfile.mkdtemp())
    src = folder / 'a.pdf'
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), 'Test')
    doc.save(src)
    doc.close()
    out = folder / 'work'
    out.mkdir()
    result = folder / 'result.json'
    payload = {
        'action': 'compress',
        'inputs': [str(src)],
        'out_dir': str(out),
        'original_name': 'a.pdf',
        'pages': None,
        'angle': None,
        'watermark': True,
    }
    completed = subprocess.run(
        [sys.executable, '-m', 'services.worker', str(result)],
        input=json.dumps(payload).encode(),
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    check(completed.returncode == 0, completed.stderr.decode()[-500:])
    data = json.loads(result.read_text())
    check(data['ok'] is True, str(data))
    check((out / data['stored_name']).exists(), 'worker fayli yo\'q')


async def test_limits() -> None:
    folder = Path(tempfile.mkdtemp())
    engine, factory = make_engine(f"sqlite+aiosqlite:///{folder / 't.db'}")
    await init_db(engine)
    async with factory() as session:
        user = await upsert_user(session, 100, 'test')
        for _ in range(3):
            await add_usage(session, user.id, 'compress')
        check(await today_count(session, user.id) == 3, 'limit hisobi')
        check(is_premium(user) is False, 'premium emas')
        await grant_premium(session, user, 30)
        check(is_premium(user) is True, 'premium yoqilmadi')
        await session.commit()
    await engine.dispose()


async def test_queue() -> None:
    queue = WorkQueue(1)
    order: list[str] = []

    async def hold() -> None:
        async with queue.slot(False):
            order.append('hold')
            await asyncio.sleep(0.05)

    async def later(name: str, premium: bool) -> None:
        async with queue.slot(premium):
            order.append(name)

    first = asyncio.create_task(hold())
    await asyncio.sleep(0.01)
    premium = asyncio.create_task(later('premium', True))
    free = asyncio.create_task(later('free', False))
    await asyncio.gather(first, premium, free)
    check(order == ['hold', 'premium', 'free'], f'navbat: {order}')


def test_locales() -> None:
    uz, ru, en = set(_CACHE['uz']), set(_CACHE['ru']), set(_CACHE['en'])
    check(uz == ru == en, f"kalitlar farq qiladi: {uz ^ ru ^ en}")
    code = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'handlers').glob('*.py'))
    code += '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'services').glob('*.py'))
    import re

    used = set(re.findall(r'\bt\(\s*[^,\n]+,\s*"([a-z0-9_]+)"', code))
    missing = sorted(key for key in used if key not in uz and not key.startswith('lang_') and not key.startswith('act_') and not key.startswith('audience_'))
    check(not missing, f"yetishmayotgan matn: {missing}")


def main() -> None:
    test_name_and_pages()
    test_thumbnail()
    test_pdf_tools()
    test_word_converter()
    test_worker()
    test_locales()
    asyncio.run(test_limits())
    asyncio.run(test_queue())
    print('Tekshiruv o\'tdi')


if __name__ == '__main__':
    main()

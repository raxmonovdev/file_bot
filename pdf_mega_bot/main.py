"""PDF Mega Botni ishga tushirish."""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from config import settings
from database.crud import activate_admin_premiums, sync_admins
from database.db import Session, init_db
from handlers import admin, convert, fallback, file_edit, pdf_tools, premium, runtime, start
from middlewares import ContextMiddleware
from services.files import reset_temp
from services.i18n import t
from services.reminders import remind_expiring

logger = logging.getLogger("pdf_mega_bot")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(settings.log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
        ],
    )


async def reminder_loop(bot: Bot) -> None:
    while True:
        try:
            await remind_expiring(bot)
        except Exception:
            logger.exception("Eslatma yuborilmadi")
        await asyncio.sleep(60 * 60)


async def set_commands(bot: Bot) -> None:
    specs = (
        ("start", "cmd_start"),
        ("menu", "cmd_menu"),
        ("profile", "cmd_profile"),
        ("premium", "cmd_premium"),
        ("help", "cmd_help"),
        ("language", "cmd_language"),
        ("cancel", "cmd_cancel"),
        ("panel", "cmd_panel"),
    )
    for code in ("uz", "ru", "en"):
        commands = [BotCommand(command=name, description=t(code, key)) for name, key in specs]
        await bot.set_my_commands(commands, language_code=code)
    await bot.set_my_commands([BotCommand(command=name, description=t("uz", key)) for name, key in specs])


async def main() -> None:
    setup_logging()
    if not settings.bot_token:
        logger.error("BOT_TOKEN yo'q. .env faylini to'ldiring.")
        return
    reset_temp()
    await init_db()
    async with Session() as session:
        await sync_admins(session, settings.admin_ids)
        await activate_admin_premiums(session)
        await session.commit()
    if not settings.admin_ids and not settings.admin_usernames:
        logger.warning("Admin yo'q. ADMIN_IDS yoki ADMIN_USERNAMES ni to'ldiring.")

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    context = ContextMiddleware()
    dp.message.middleware(context)
    dp.callback_query.middleware(context)
    dp.include_routers(
        start.router,
        admin.router,
        premium.router,
        file_edit.router,
        pdf_tools.router,
        convert.router,
        runtime.router,
        fallback.router,
    )

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        logger.exception("Yangilanish xatosi: %s", event.exception)

    asyncio.create_task(reminder_loop(bot))
    try:
        await set_commands(bot)
    except Exception:
        logger.exception("Buyruqlar ro'yxati yangilanmadi")
    logger.info("Bot ishga tushdi")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Bazaga ulanish. Boshida SQLite, keyin DATABASE_URL ni almashtirish mumkin."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from database.models import Base

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(engine, expire_on_commit=False)


def make_engine(url: str):
    eng = create_async_engine(url)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    return eng, factory


async def init_db(eng=engine) -> None:
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

"""Premium ishlar bo'sh joy ochilganda oddiy navbatdan oldin olinadi."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class WorkQueue:
    def __init__(self, slots: int) -> None:
        self.slots = max(1, slots)
        self.active = 0
        self.premium_waiting = 0
        self._cond = asyncio.Condition()

    async def acquire(self, premium: bool) -> None:
        async with self._cond:
            if premium:
                self.premium_waiting += 1
            try:
                while self.active >= self.slots or (not premium and self.premium_waiting > 0):
                    await self._cond.wait()
            finally:
                if premium:
                    self.premium_waiting -= 1
            self.active += 1

    async def release(self) -> None:
        async with self._cond:
            self.active = max(0, self.active - 1)
            self._cond.notify_all()

    @asynccontextmanager
    async def slot(self, premium: bool) -> AsyncIterator[None]:
        await self.acquire(premium)
        try:
            yield
        finally:
            await self.release()


class BusySet:
    """Bitta foydalanuvchida bir vaqtning o'zida bitta ish."""

    def __init__(self) -> None:
        self._users: set[int] = set()
        self._lock = asyncio.Lock()

    async def try_enter(self, user_id: int) -> bool:
        async with self._lock:
            if user_id in self._users:
                return False
            self._users.add(user_id)
            return True

    async def leave(self, user_id: int) -> None:
        async with self._lock:
            self._users.discard(user_id)

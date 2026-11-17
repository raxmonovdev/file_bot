"""Foydalanuvchiga ko'rsatiladigan xato. Kalit locales ichidan olinadi."""

from __future__ import annotations


class UserFacingError(Exception):
    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key = key
        self.params = params

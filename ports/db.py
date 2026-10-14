"""Persistence port: the AI implements adapters, the domain only knows this."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.transfer import Account


class DbWrite(Protocol):
    def save(self, account: Account) -> None: ...

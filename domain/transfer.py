"""Balance transfer between accounts (pure logic)."""

from dataclasses import dataclass, replace
from decimal import Decimal

from aif import contract
from ports.db import DbWrite


@dataclass(frozen=True)
class Account:
    id: str
    balance: Decimal


@dataclass(frozen=True)
class TransferResult:
    source: Account
    target: Account


@contract(
    requires=lambda source, amount: amount > 0 and source.balance >= amount,
    ensures=lambda r, source, target: (
        r.source.balance + r.target.balance == source.balance + target.balance and r.source.balance >= 0
    ),
    effects=[],
)
def transfer(source: Account, target: Account, amount: Decimal) -> TransferResult:
    """Move `amount` from source to target without creating or destroying money."""
    return TransferResult(
        source=replace(source, balance=source.balance - amount),
        target=replace(target, balance=target.balance + amount),
    )


@contract(effects=["db.write"])
def persist(result: TransferResult, db: DbWrite) -> None:
    """Save both accounts through the injected capability."""
    db.save(result.source)
    db.save(result.target)

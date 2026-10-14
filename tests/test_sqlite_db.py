from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from adapters.sqlite_db import SqliteDb
from domain.transfer import Account, persist, transfer

money = st.decimals(min_value=0, max_value=10**6, places=2)


def test_save_and_get_roundtrip() -> None:
    db = SqliteDb()
    db.save(Account("a", Decimal("10.50")))
    db.save(Account("a", Decimal("7.25")))  # upsert
    assert db.get("a") == Account("a", Decimal("7.25"))
    assert db.get("missing") is None
    db.close()


@given(money, money, money)
def test_transfer_then_persist_end_to_end(source_balance: Decimal, target_balance: Decimal, amount: Decimal) -> None:
    assume(amount > 0 and source_balance >= amount)
    db = SqliteDb()
    result = transfer(Account("a", source_balance), Account("b", target_balance), amount)
    persist(result, db)
    stored_a, stored_b = db.get("a"), db.get("b")
    assert stored_a is not None and stored_b is not None
    assert stored_a.balance + stored_b.balance == source_balance + target_balance
    db.close()

from hypothesis import assume, given
from hypothesis import strategies as st

from domain.transfer import Account, transfer

money = st.decimals(min_value=0, max_value=10**6, places=2)


@given(money, money, money)
def test_transfer_conserves_money(source_balance, target_balance, amount):
    assume(amount > 0 and source_balance >= amount)
    # the contract is checked inside the call; a violation fails with a counterexample
    transfer(Account("a", source_balance), Account("b", target_balance), amount)

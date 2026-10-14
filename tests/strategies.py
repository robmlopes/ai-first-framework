"""Input domains for `aif fuzz`: types registered here are used wherever they appear in a contract signature."""

from decimal import Decimal

from hypothesis import strategies as st

# Money has two decimal places and a bounded magnitude; unbounded Decimals overflow the 28-digit context.
MONEY = st.decimals(min_value=0, max_value=10**9, places=2)
st.register_type_strategy(Decimal, MONEY)

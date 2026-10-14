from __future__ import annotations

import pytest

from aif import ContractViolation, contract


@contract(requires=lambda x: x > 0, ensures=lambda r, x: r == x * 2, effects=[])
def double(x: int) -> int:
    return x * 2


@contract(ensures=lambda r, x: r == x)
def broken(x: int) -> int:
    return x + 1


def test_valid_call_passes() -> None:
    assert double(3) == 6


def test_precondition_violation_has_counterexample() -> None:
    with pytest.raises(ContractViolation) as exc:
        double(-1)
    assert exc.value.kind == "precondition"
    assert exc.value.counterexample == {"inputs": {"x": -1}}


def test_postcondition_violation_includes_result() -> None:
    with pytest.raises(ContractViolation) as exc:
        broken(1)
    assert exc.value.kind == "postcondition"
    assert exc.value.counterexample == {"inputs": {"x": 1}, "result": 2}
    assert str(exc.value).startswith("AIF_CONTRACT {")


def test_effects_exposed_on_wrapper() -> None:
    assert getattr(double, "__aif__")["effects"] == []  # noqa: B009


def test_contracts_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIF_CONTRACTS", "off")
    assert broken(1) == 2
    assert double(-5) == -10


def test_lambda_may_name_subset_of_params() -> None:
    @contract(requires=lambda b: b > 0)
    def f(a: int, b: int) -> int:
        return a + b

    assert f(1, 2) == 3
    with pytest.raises(ContractViolation):
        f(1, 0)

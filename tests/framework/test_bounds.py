from __future__ import annotations

from aif.bounds import infer
from tests.framework.conftest import Project


def test_lower_and_chained_bounds() -> None:
    assert infer(lambda price, percent: price >= 0 and 0 <= percent <= 100) == {"price": (0, None), "percent": (0, 100)}


def test_strict_comparisons_are_tightened() -> None:
    assert infer(lambda x: x > 5 and x < 10) == {"x": (6, 9)}


def test_constant_on_the_left_is_flipped() -> None:
    assert infer(lambda a: a >= 3) == {"a": (3, None)}
    assert infer(lambda a: a < 3) == {"a": (None, 2)}


def test_negative_constants_and_equality() -> None:
    assert infer(lambda x: -10 <= x <= -1) == {"x": (-10, -1)}
    assert infer(lambda x: x == 7) == {"x": (7, 7)}


def test_tightest_bound_wins() -> None:
    assert infer(lambda x: x >= 1 and x >= 5 and x <= 9 and x <= 8) == {"x": (5, 8)}


def test_uninferable_predicates_give_nothing() -> None:
    assert infer(lambda s: len(s) > 0) == {}
    assert infer(lambda x: x >= 0 or x < -5) == {}
    assert infer(lambda a, b: a < b) == {}
    assert infer(lambda b: b != 0) == {}
    assert infer(None) == {}


def test_other_conjuncts_do_not_hide_bounds() -> None:
    assert infer(lambda x, s: x >= 0 and len(s) > 0) == {"x": (0, None)}


def test_contradictory_range_is_dropped_not_crashing() -> None:
    assert infer(lambda x: x > 5 and x < 3) == {}


def test_booleans_are_not_treated_as_ints() -> None:
    assert infer(lambda x: x >= True) == {}  # noqa: FBT003


def test_fuzz_hits_a_narrow_range_without_strategies(project: Project) -> None:
    from aif import fuzz

    src = (
        "from aif import contract\n\n\n"
        "@contract(requires=lambda x: x == 123456, ensures=lambda r, x: r == x)\n"
        "def f(x: int) -> int:\n    return x\n"
    )
    project.write("domain/m.py", src)
    assert fuzz.run(project.root, project.cfg) == []


def test_fuzz_still_finds_bug_inside_inferred_range(project: Project) -> None:
    from aif import fuzz

    src = (
        "from aif import contract\n\n\n"
        "@contract(requires=lambda x: 0 <= x <= 100, ensures=lambda r, x: r <= 100)\n"
        "def f(x: int) -> int:\n    return x * 2\n"
    )
    project.write("domain/m.py", src)
    (err,) = fuzz.run(project.root, project.cfg)
    assert err["rule"] == "CON001" and 50 < int(err["counterexample"]["inputs"]["x"]) <= 100

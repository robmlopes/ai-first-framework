from __future__ import annotations

import re
from typing import Any

from aif import fuzz
from tests.framework.conftest import Project

HEAD = "from aif import contract\n\n\n"


def run(project: Project, src: str, **options: str) -> list[dict[str, Any]]:
    if options:
        text = (project.root / "aif.toml").read_text()
        for k, v in options.items():
            text = re.sub(rf"^{k} = .*\n", "", text, flags=re.M).replace("[aif]\n", f"[aif]\n{k} = {v}\n", 1)
        project.write("aif.toml", text)
    project.write("domain/m.py", HEAD + src)
    return fuzz.run(project.root, project.cfg)


def rules(project: Project, src: str, **options: str) -> list[str]:
    return [e["rule"] for e in run(project, src, **options)]


def test_correct_contract_passes(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r > x)\ndef inc(x: int) -> int:\n    return x + 1\n"
    assert run(project, src) == []


def test_con001_wrong_implementation_with_counterexample(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r > x)\ndef inc(x: int) -> int:\n    return x - 1\n"
    (err,) = run(project, src)
    assert err["rule"] == "CON001" and err["stage"] == "fuzz"
    assert "x" in err["counterexample"]["inputs"] and "result" in err["counterexample"]
    assert err["file"].endswith("domain/m.py") and err["line"] >= 1


def test_con001_bug_only_on_rare_branch_is_found(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r >= 0)\ndef f(x: int) -> int:\n    return -1 if x == 0 else abs(x)\n"
    assert rules(project, src) == ["CON001"]


def test_requires_filters_inputs(project: Project) -> None:
    src = "@contract(requires=lambda x: x != 0, ensures=lambda r, x: r > 0)\ndef f(x: int) -> int:\n    return abs(x)\n"
    assert run(project, src) == []


def test_con002_raises_on_valid_input(project: Project) -> None:
    src = (
        "from hypothesis import strategies as st\n\n\n"
        "@contract(requires=lambda x: x >= 0, ensures=lambda r: True, strategies={'x': st.integers(0, 10)})\n"
        "def f(x: int) -> int:\n    return 10 // (x - 3)\n"
    )
    (err,) = run(project, src)
    assert err["rule"] == "CON002" and "ZeroDivisionError" in err["cause"]
    assert err["counterexample"]["inputs"] == {"x": "3"}


def test_con003_unannotated_parameter(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: True)\ndef f(x):  # type: ignore[no-untyped-def]\n    return x\n"
    (err,) = run(project, src)
    assert err["rule"] == "CON003" and "strategies" in err["suggestion"]


def test_con004_unsatisfiable_requires(project: Project) -> None:
    src = "@contract(requires=lambda x: x > 5 and x < 3, ensures=lambda r: True)\ndef f(x: int) -> int:\n    return x\n"
    assert rules(project, src) == ["CON004"]


def test_explicit_strategies_override_hints(project: Project) -> None:
    src = (
        "from hypothesis import strategies as st\n\n\n"
        "@contract(requires=lambda x: x == 7, ensures=lambda r, x: r == 7, strategies={'x': st.just(7)})\n"
        "def f(x: int) -> int:\n    return x\n"
    )
    assert run(project, src) == []


def test_narrow_requires_is_now_reachable_through_inferred_bounds(project: Project) -> None:
    narrow = "@contract(requires=lambda x: x == 123456, ensures=lambda r: True)\ndef f(x: int) -> int:\n    return x\n"
    assert rules(project, narrow) == []


def test_con004_when_bounds_cannot_be_inferred(project: Project) -> None:
    src = (
        "@contract(requires=lambda s: s == 'unlikely-value', ensures=lambda r: True)\n"
        "def f(s: str) -> str:\n    return s\n"
    )
    assert rules(project, src) == ["CON004"]


def test_functions_with_effects_are_skipped(project: Project) -> None:
    src = (
        "from ports.db import DbWrite\n\n\n"
        "@contract(effects=['db.write'], ensures=lambda r: False)\n"
        "def f(db: DbWrite) -> None:\n    return None\n"
    )
    assert run(project, src) == []


def test_contracts_without_ensures_are_skipped(project: Project) -> None:
    assert run(project, "@contract(requires=lambda x: x > 0)\ndef f(x: int) -> int:\n    raise RuntimeError\n") == []


def test_can_be_disabled(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r > x)\ndef inc(x: int) -> int:\n    return x - 1\n"
    assert run(project, src, fuzz="false") == []


def test_float_inputs_are_finite_by_default(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r == r)\ndef f(x: float) -> float:\n    return x * 2\n"
    assert run(project, src) == []


def test_setup_module_registers_domain_strategies(project: Project) -> None:
    project.write(
        "tests/strat.py",
        "from hypothesis import strategies as st\n\n"
        "st.register_type_strategy(int, st.integers(min_value=1, max_value=3))\n",
    )
    src = "@contract(ensures=lambda r, x: x <= 3)\ndef f(x: int) -> int:\n    return x\n"
    assert run(project, src, fuzz_setup='"tests.strat"') == []
    bad = src.replace("x <= 3", "x <= 2")
    assert rules(project, bad, fuzz_setup='"tests.strat"') == ["CON001"]


def test_import_error_in_module_is_reported_not_crashed(project: Project) -> None:
    (err,) = run(project, "import nothing_here_xyz\n")
    assert err["rule"] == "CON005" and "nothing_here_xyz" in err["cause"]


def test_deterministic_across_runs(project: Project) -> None:
    src = "@contract(ensures=lambda r, x: r != 42)\ndef f(x: int) -> int:\n    return x\n"
    first = run(project, src)
    assert first == run(project, src)

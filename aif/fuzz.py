"""Contract fuzzing: checks every `@contract(ensures=...)` against generated inputs, without hand-written tests.

Inputs come from the type hints (Hypothesis `from_type`, finite numbers by default), narrowed by the integer
ranges that `requires` states (see `aif.bounds`). A `strategies=` mapping on the contract, or types registered
by the `fuzz_setup` module, override that. Inputs that violate `requires` are discarded. Functions with declared
effects are skipped (they need real ports).
Runs in a subprocess so a crashing or noisy module cannot corrupt the caller. Rules:

CON001  `ensures` failed for inputs that satisfy `requires` (counterexample included)
CON002  the function raised for inputs that satisfy `requires`
CON003  inputs cannot be generated from the type hints
CON004  `requires` rejects (almost) every generated input, so the contract is untestable or contradictory
CON005  the fuzz worker itself failed (e.g. a module cannot be imported)
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import typing
from pathlib import Path
from typing import Any

from aif import cache
from aif.bounds import infer as bounds_of
from aif.config import Config
from aif.index import module_of, source_files

Error = dict[str, Any]
_PORT_MARKER = "ports"


def _error(rule: str, module: str, fn: Any, cause: str, suggestion: str, **extra: Any) -> Error:
    try:
        line = inspect.getsourcelines(inspect.unwrap(fn))[1]
        file = Path(inspect.getsourcefile(inspect.unwrap(fn)) or module).as_posix()
    except (OSError, TypeError):
        line, file = 1, module
    return {
        "stage": "fuzz",
        "rule": rule,
        "file": file,
        "line": line,
        "cause": cause,
        "suggestion": suggestion,
        **extra,
    }


def run(root: Path, cfg: Config, use_cache: bool = False) -> list[Error]:
    """Fuzz every contract; with `use_cache`, modules whose inputs are unchanged since a passing run are skipped."""
    if not cfg.fuzz:
        return []
    files = {
        module_of(root, f): f
        for f in source_files(root, cfg)
        if f.name != "__init__.py" and f.relative_to(root).parts[0] not in cfg.port_dirs
    }
    keys = cache.keys(root, cfg) if use_cache else {}
    passed = cache.load(root) if use_cache else {}
    modules = [m for m in files if not (use_cache and passed.get(m) == keys.get(m))]
    errors = _run_worker(root, cfg, modules) if modules else []
    if use_cache and not any(not e.get("file") for e in errors):
        failing = {Path(e["file"]).resolve() for e in errors}
        fresh = {m: keys[m] for m in modules if files[m].resolve() not in failing}
        cache.save(root, {**{m: k for m, k in passed.items() if m in files}, **fresh})
    return errors


def _run_worker(root: Path, cfg: Config, modules: list[str]) -> list[Error]:
    framework_parent = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": f"{root}:{framework_parent}", "PYTHONDONTWRITEBYTECODE": "1"}
    payload = json.dumps(
        {"modules": modules, "examples": cfg.fuzz_examples, "finite": cfg.fuzz_finite_numbers, "setup": cfg.fuzz_setup}
    )
    proc = subprocess.run(
        [sys.executable, "-m", "aif.fuzz", payload], cwd=root, env=env, capture_output=True, text=True, check=False
    )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]
    except (IndexError, json.JSONDecodeError):
        return [
            {
                "stage": "fuzz",
                "rule": "CON005",
                "file": "",
                "line": 0,
                "cause": f"fuzz worker failed: {(proc.stderr or proc.stdout).strip()[-400:]}",
                "suggestion": "run `python -m aif.fuzz` manually to debug",
            }
        ]


# ---- worker -----------------------------------------------------------------------------------------------
def _targets(modules: list[str]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for name in modules:
        mod = importlib.import_module(name)
        for fn in vars(mod).values():
            meta = getattr(fn, "__aif__", None)
            if callable(fn) and meta and fn.__module__ == name and meta.get("ensures") and not meta["effects"]:
                out.append((name, fn))
    return out


def _strategy(hint: Any, override: Any, bound: Any = None) -> Any:
    from hypothesis import strategies as st

    if override is not None:
        return override
    if bound is not None and hint is int:
        return st.integers(min_value=bound[0], max_value=bound[1])
    if bound is not None and hint is float:
        low = None if bound[0] is None else float(bound[0])
        high = None if bound[1] is None else float(bound[1])
        return st.floats(min_value=low, max_value=high, allow_nan=False, allow_infinity=False)
    return st.from_type(hint)


def _check(name: str, fn: Any, examples: int) -> list[Error]:
    import hypothesis
    from hypothesis import given, settings
    from hypothesis import strategies as st
    from hypothesis.errors import FailedHealthCheck, Unsatisfiable

    from aif.contract import _call

    meta = fn.__aif__
    raw = inspect.unwrap(fn)
    hints = typing.get_type_hints(raw)
    params = [p for p in inspect.signature(raw).parameters.values()]
    missing = [p.name for p in params if p.name not in hints and p.name not in meta["strategies"]]
    try:
        if missing:
            raise TypeError(f"no type hint for {missing}")
        bounds = bounds_of(meta["requires"])
        strategy = st.fixed_dictionaries(
            {p.name: _strategy(hints[p.name], meta["strategies"].get(p.name), bounds.get(p.name)) for p in params}
        )
    except Exception as exc:
        return [
            _error(
                "CON003",
                name,
                fn,
                f"cannot generate inputs for {name}.{raw.__name__}: {type(exc).__name__}: {exc}",
                f"annotate {missing or 'the parameters'} or pass strategies={{'param': st....}} to @contract",
            )
        ]
    seen = {"ok": 0}
    failure: dict[str, Any] = {}

    @settings(
        max_examples=examples,
        database=None,
        deadline=None,
        derandomize=True,
        suppress_health_check=[hypothesis.HealthCheck.too_slow, hypothesis.HealthCheck.data_too_large],
    )
    @given(strategy)
    def prop(inputs: dict[str, Any]) -> None:
        requires = meta["requires"]
        if requires is not None:
            hypothesis.assume(_call(requires, inputs))
        seen["ok"] += 1
        failure.clear()
        failure["inputs"] = inputs
        result = raw(**inputs)
        failure["result"] = result
        if not _call(meta["ensures"], inputs, result):
            failure["kind"] = "post"
            raise AssertionError("postcondition")
        failure.clear()

    try:
        prop()
    except (FailedHealthCheck, Unsatisfiable):
        return [
            _error(
                "CON004",
                name,
                fn,
                f"{raw.__name__}: `requires` rejected (almost) every generated input",
                "relax `requires`, or pass strategies= that produce valid inputs",
            )
        ]
    except BaseException as exc:
        shown = {k: repr(v) for k, v in failure.get("inputs", {}).items()}
        if failure.get("kind") == "post":
            return [
                _error(
                    "CON001",
                    name,
                    fn,
                    f"postcondition of {raw.__name__} failed for inputs satisfying `requires`",
                    "fix the implementation or the `ensures` clause",
                    counterexample={"inputs": shown, "result": repr(failure.get("result"))},
                )
            ]
        return [
            _error(
                "CON002",
                name,
                fn,
                f"{raw.__name__} raised {type(exc).__name__}: {exc} for inputs satisfying `requires`",
                "tighten `requires` to exclude the input, or handle it in the implementation",
                counterexample={"inputs": shown},
            )
        ]
    if seen["ok"] == 0:
        return [
            _error("CON004", name, fn, f"{raw.__name__}: no generated input satisfied `requires`", "relax `requires`")
        ]
    return []


def _load_setup(dotted: str) -> None:
    """Import the module that registers domain strategies; works with or without `__init__.py` packages."""
    try:
        importlib.import_module(dotted)
        return
    except ModuleNotFoundError:
        path = Path.cwd().joinpath(*dotted.split(".")).with_suffix(".py")
        if not path.is_file():
            raise
    spec = importlib.util.spec_from_file_location(dotted, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    spec.loader.exec_module(module)


def main(payload: str) -> int:
    cfg = json.loads(payload)
    from decimal import Decimal

    from hypothesis import strategies as st

    if cfg["finite"]:
        st.register_type_strategy(float, st.floats(allow_nan=False, allow_infinity=False))
        st.register_type_strategy(Decimal, st.decimals(allow_nan=False, allow_infinity=False))
    if cfg.get("setup"):
        _load_setup(cfg["setup"])
    errors: list[Error] = []
    for name, fn in _targets(cfg["modules"]):
        errors += _check(name, fn, cfg["examples"])
    sys.stdout.write("\n" + json.dumps(errors) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

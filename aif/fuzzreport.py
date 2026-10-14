"""`aif fuzz --report`: what contract fuzzing tested, what it skipped, and why.

Skips are found statically from the AST (the worker only imports what it can fuzz), so a function that is
silently not covered shows up here instead of being invisible.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any

from aif import effects
from aif.config import Config
from aif.index import module_of, source_files

Entry = dict[str, Any]
_NO_ENSURES = "contract has no `ensures`: nothing to check"
_EFFECTS = "declares effects: needs real ports, covered by integration tests"
_NO_CONTRACT = "no @contract"


def _contract_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "contract":
            return d
    return None


def _reason(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    call = _contract_call(node)
    if call is None:
        return _NO_CONTRACT
    if effects.declared(node):
        return _EFFECTS
    if not any(kw.arg == "ensures" for kw in call.keywords):
        return _NO_ENSURES
    return None


def skipped(root: Path, cfg: Config, fuzzed: set[str]) -> list[Entry]:
    """Top-level functions that fuzzing does not cover, with the reason."""
    out: list[Entry] = []
    for file in source_files(root, cfg):
        rel = file.relative_to(root).as_posix()
        if file.name == "__init__.py" or rel.split("/")[0] in cfg.port_dirs:
            continue
        module = module_of(root, file)
        for node in ast.parse(file.read_text(encoding="utf-8")).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or f"{module}.{node.name}" in fuzzed:
                continue
            reason = _reason(node)
            if reason is None:
                reason = "not reached by the worker (not a top-level function of an importable module)"
            elif reason == _NO_CONTRACT and node.name.startswith("_"):
                continue  # private helpers are not part of the contract surface
            out.append({"module": module, "function": node.name, "line": node.lineno, "file": rel, "reason": reason})
    return out


def build(root: Path, cfg: Config, errors: list[Entry], tested: list[Entry]) -> dict[str, Any]:
    fuzzed = {f"{t['module']}.{t['function']}" for t in tested}
    skips = skipped(root, cfg, fuzzed)
    reasons = Counter(s["reason"] for s in skips)
    return {
        "ok": not errors,
        "errors": errors,
        "tested": tested,
        "skipped": skips,
        "summary": {
            "functions_fuzzed": len(tested),
            "examples_run": sum(int(t.get("examples", 0)) for t in tested),
            "failed": sum(1 for t in tested if t["status"] != "passed"),
            "skipped": len(skips),
            "skipped_by_reason": dict(reasons),
            "config": {"fuzz": cfg.fuzz, "fuzz_examples": cfg.fuzz_examples},
        },
    }

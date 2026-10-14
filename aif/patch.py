"""aif patch: replace one function, class or method (`Class.method`) instead of rewriting the file."""

from __future__ import annotations

import ast
import difflib
import textwrap
from pathlib import Path
from typing import Any

from aif import lint
from aif.config import Config

Definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
Result = dict[str, Any]


def _fail(cause: str, suggestion: str = "") -> Result:
    return {"ok": False, "stage": "patch", "cause": cause, "suggestion": suggestion}


def _span(node: Definition) -> tuple[int, int]:
    """1-based inclusive line span, decorators included."""
    start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
    return start, node.end_lineno or node.lineno


def _find(tree: ast.Module, symbol: str) -> Definition | None:
    """Find `name` at top level, or `Class.method` inside a top-level class."""
    owner, _, member = symbol.partition(".")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == owner:
            if not member:
                return node
            if isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == member:
                        return m
    return None


def _validate_new(source: str, symbol: str) -> str | None:
    """Return an error message, or None when `source` is exactly one definition named `symbol`."""
    name = symbol.rpartition(".")[2]
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError as e:
        return f"new source has a syntax error at line {e.lineno}: {e.msg}"
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return "new source must contain exactly one top-level function or class"
    if "." in symbol and not isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "a method patch must contain a function, not a class"
    if tree.body[0].name != name:
        return f"new source defines '{tree.body[0].name}', expected '{name}'"
    return None


def apply(
    root: Path, cfg: Config, file: str, symbol: str, new_source: str, dry_run: bool = False, keep: bool = False
) -> Result:
    target = (root / file).resolve()
    if (
        not target.is_relative_to(root)
        or target.suffix != ".py"
        or cfg.layer(target.relative_to(root).as_posix()) not in cfg.source_dirs
    ):
        return _fail(f"{file} is not a Python file inside {cfg.source_dirs}", "patch only project source files")
    if not target.exists():
        return _fail(f"{file} does not exist", "check .aif/index.json for module paths")
    problem = _validate_new(new_source, symbol)
    if problem:
        return _fail(problem, "send the complete definition, decorators included")
    old_text = target.read_text(encoding="utf-8")
    node = _find(ast.parse(old_text), symbol)
    if node is None:
        return _fail(f"'{symbol}' not found in {file}", "see .aif/index.json for existing symbols")
    start, end = _span(node)
    lines = old_text.splitlines(keepends=True)
    body = textwrap.indent(textwrap.dedent(new_source).rstrip("\n"), " " * node.col_offset)
    new_text = "".join(lines[: start - 1]) + body + "\n" + "".join(lines[end:])
    diff = "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), f"a/{file}", f"b/{file}"))
    result: Result = {"ok": True, "file": file, "symbol": symbol, "lines_replaced": [start, end], "diff": diff}
    if dry_run:
        return result | {"dry_run": True}
    target.write_text(new_text, encoding="utf-8")
    errors = lint.run(root, cfg)
    if errors and not keep:
        target.write_text(old_text, encoding="utf-8")
        return result | {"ok": False, "rolled_back": True, "errors": errors}
    return result | {"errors": errors}

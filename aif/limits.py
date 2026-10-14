"""AIF005 size limits: code lines only, per-layer limits, early warnings and extraction hints."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from aif.config import Config
from aif.index import source_files

Error = dict[str, Any]
Function = ast.FunctionDef | ast.AsyncFunctionDef
_COMPOUND = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)
_MIN_WARN_LIMIT = 10


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            first = n.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def _size(lines: list[str], start: int, end: int, skip: set[int], cfg: Config) -> int:
    if not cfg.count_code_lines:
        return end - start + 1
    return sum(
        1
        for i in range(start, end + 1)
        if i not in skip and lines[i - 1].strip() and not lines[i - 1].strip().startswith("#")
    )


def _hint(node: Function, lines: list[str], skip: set[int], cfg: Config) -> str:
    blocks = [
        (_size(lines, s.lineno, s.end_lineno or s.lineno, skip, cfg), s) for s in node.body if isinstance(s, _COMPOUND)
    ]
    top = sorted(blocks, key=lambda b: -b[0])[:2]
    if not top:
        return "split into smaller functions"
    found = ", ".join(f"{type(s).__name__.lower()} at line {s.lineno} ({n} lines)" for n, s in top)
    return f"extract a helper; largest blocks: {found}"


def _entry(rule: str, file: str, line: int, cause: str, suggestion: str, warning: bool) -> Error:
    err: Error = {"stage": "lint", "rule": rule, "file": file, "line": line, "cause": cause, "suggestion": suggestion}
    if warning:
        err["severity"] = "warning"
    return err


def _judge(name: str, size: int, limit: int, cfg: Config) -> str | None:
    """'error', 'warning' or None for a measured size against its limit."""
    if size > limit:
        return "error"
    return "warning" if limit >= _MIN_WARN_LIMIT and size > limit * cfg.limit_warn_ratio else None


def check_file(tree: ast.Module, text: str, rel: str, cfg: Config) -> tuple[list[Error], list[Error]]:
    """(errors, warnings) for one file. Limits come from `[aif.limits.<layer>]` or the global values."""
    lines, skip = text.splitlines(), _docstring_lines(tree)
    errors: list[Error] = []
    warnings: list[Error] = []

    def report(kind: str | None, line: int, what: str, size: int, limit: int, hint: str) -> None:
        if kind is None:
            return
        counted = "code lines" if cfg.count_code_lines else "lines"
        cause = f"{what} has {size} {counted} (max {limit})"
        (errors if kind == "error" else warnings).append(_entry("AIF005", rel, line, cause, hint, kind == "warning"))

    flimit = cfg.limit(rel, "max_file_lines")
    fsize = _size(lines, 1, max(len(lines), 1), skip, cfg) if lines else 0
    report(_judge("file", fsize, flimit, cfg), 1, "file", fsize, flimit, "split the module")
    limit = cfg.limit(rel, "max_function_lines")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size = _size(lines, node.lineno, node.end_lineno or node.lineno, skip, cfg)
            kind = _judge(node.name, size, limit, cfg)
            report(kind, node.lineno, node.name, size, limit, _hint(node, lines, skip, cfg) if kind else "")
    return errors, warnings


def warnings(root: Path, cfg: Config, only: frozenset[str] | None = None) -> list[Error]:
    """Functions and files that are close to their limit but still pass."""
    out: list[Error] = []
    for file in source_files(root, cfg):
        rel = file.relative_to(root).as_posix()
        if only is not None and rel not in only:
            continue
        text = file.read_text(encoding="utf-8")
        out += check_file(ast.parse(text), text, rel, cfg)[1]
    return out

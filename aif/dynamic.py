"""Dynamic-dispatch checks for pure modules: references to banned names and runtime-bound calls."""

from __future__ import annotations

import ast
from typing import Any

from aif.config import Config

Error = dict[str, Any]
Function = ast.FunctionDef | ast.AsyncFunctionDef
_DYNAMIC_VALUES = (ast.Call, ast.Subscript, ast.IfExp, ast.BoolOp, ast.Await, ast.NamedExpr)


def _error(rule: str, file: str, line: int, cause: str, suggestion: str) -> Error:
    return {"stage": "effects", "rule": rule, "file": file, "line": line, "cause": cause, "suggestion": suggestion}


def is_banned(full: str, cfg: Config) -> bool:
    """True when a resolved dotted name is a banned builtin or lives in a banned module."""
    short = full.removeprefix("builtins.")
    banned_builtin = short in cfg.forbidden_calls or (full != short and short.split(".")[0] in cfg.forbidden_calls)
    banned_module = "." in full and full.split(".")[0] in cfg.forbidden_imports
    return banned_builtin or banned_module or full in cfg.forbidden_clock


def banned_references(
    tree: ast.Module, rel: str, cfg: Config, resolve: Any, dotted: Any, aliases: dict[str, str]
) -> list[Error]:
    """AIF010 for banned names used as values (`f = open`, `map(os.getcwd, xs)`), not only called."""
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    inner = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    errors: list[Error] = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Name, ast.Attribute)) or id(n) in called or id(n) in inner:
            continue
        if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load):
            continue
        full = resolve(dotted(n), aliases)
        if full and is_banned(full, cfg):
            errors.append(_error("AIF010", rel, n.lineno, f"reference to effect: {full}", "use an injected port"))
    return errors


def _own_nodes(fn: Function) -> list[ast.AST]:
    """Nodes of `fn` excluding the bodies of nested functions and classes."""
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(fn.body)
    while stack:
        n = stack.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))
    return out


def _bound_dynamically(fn: Function) -> dict[str, int]:
    """Local names whose value comes from a call/subscript/branch/loop, with the binding line."""
    dynamic: dict[str, int] = {}
    static: set[str] = set()
    for n in _own_nodes(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    (dynamic.setdefault(t.id, n.lineno) if isinstance(n.value, _DYNAMIC_VALUES) else static.add(t.id))
        elif isinstance(n, (ast.For, ast.AsyncFor)) and isinstance(n.target, ast.Name):
            dynamic.setdefault(n.target.id, n.lineno)
    return {k: v for k, v in dynamic.items() if k not in static}


def dynamic_calls(tree: ast.Module, rel: str) -> list[Error]:
    """AIF013: callee decided at runtime (`fn = pick(); fn()`, `table[k]()`, `make()()`)."""
    errors: list[Error] = []
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        local = _bound_dynamically(fn)
        for n in _own_nodes(fn):
            if not isinstance(n, ast.Call):
                continue
            callee = n.func
            if isinstance(callee, (ast.Subscript, ast.Call)):
                kind = "subscript" if isinstance(callee, ast.Subscript) else "call result"
                errors.append(_dynamic(rel, n.lineno, f"call through a {kind}"))
            elif isinstance(callee, ast.Name) and callee.id in local:
                errors.append(
                    _dynamic(rel, n.lineno, f"call through '{callee.id}', bound at runtime on line {local[callee.id]}")
                )
    return errors


def _dynamic(rel: str, line: int, cause: str) -> Error:
    return _error(
        "AIF013", rel, line, f"dynamic dispatch: {cause}", "call a named function, or inject the behaviour as a port"
    )

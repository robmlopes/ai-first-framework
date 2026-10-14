"""Infer numeric input ranges from a `requires` lambda, so fuzzing hits the valid region.

`requires=lambda price, percent: price >= 0 and 0 <= percent <= 100` yields
`{"price": (0, None), "percent": (0, 100)}`. Only simple comparisons of a parameter with an integer
constant are used, joined by `and`; anything else is ignored (the predicate still filters afterwards).
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable
from typing import Any

Bound = tuple[int | None, int | None]
_FLIP = {ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt, ast.GtE: ast.LtE}


def _constant(node: ast.expr) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _constant(node.operand)
        return -inner if inner is not None else None
    return None


def _apply(bounds: dict[str, list[int | None]], name: str, op: type[ast.cmpop], value: int) -> None:
    low_high = bounds.setdefault(name, [None, None])
    if op is ast.Gt:
        value, op = value + 1, ast.GtE
    elif op is ast.Lt:
        value, op = value - 1, ast.LtE
    if op is ast.GtE:
        low_high[0] = value if low_high[0] is None else max(low_high[0], value)
    elif op is ast.LtE:
        low_high[1] = value if low_high[1] is None else min(low_high[1], value)
    elif op is ast.Eq:
        low_high[0] = low_high[1] = value


def _compare(node: ast.Compare, params: set[str], bounds: dict[str, list[int | None]]) -> None:
    operands = [node.left, *node.comparators]
    for op, left, right in zip(node.ops, operands[:-1], operands[1:], strict=True):
        if isinstance(left, ast.Name) and left.id in params and (c := _constant(right)) is not None:
            _apply(bounds, left.id, type(op), c)
        elif isinstance(right, ast.Name) and right.id in params and (c := _constant(left)) is not None:
            flipped = _FLIP.get(type(op), type(op))
            _apply(bounds, right.id, flipped, c)


def _conjuncts(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [part for v in node.values for part in _conjuncts(v)]
    return [node]


def _lambda_of(fn: Callable[..., Any]) -> ast.Lambda | None:
    try:
        source = textwrap.dedent(inspect.getsource(fn)).strip()
    except (OSError, TypeError):
        return None
    for candidate in (source, "(" + source + ")", source.split("=", 1)[-1].strip().rstrip(",")):
        try:
            tree = ast.parse(candidate)
        except SyntaxError:
            continue
        lambdas = [n for n in ast.walk(tree) if isinstance(n, ast.Lambda)]
        if len(lambdas) == 1 or any(len(n.args.args) == len(inspect.signature(fn).parameters) for n in lambdas):
            matching = [n for n in lambdas if [a.arg for a in n.args.args] == list(inspect.signature(fn).parameters)]
            return matching[0] if matching else None
    return None


def infer(requires: Callable[..., Any] | None) -> dict[str, Bound]:
    """Per-parameter `(low, high)` integer bounds implied by `requires`; empty when nothing can be inferred."""
    if requires is None:
        return {}
    node = _lambda_of(requires)
    if node is None:
        return {}
    params = {a.arg for a in node.args.args}
    bounds: dict[str, list[int | None]] = {}
    for part in _conjuncts(node.body):
        if isinstance(part, ast.Compare):
            _compare(part, params, bounds)
    # a crossed range (x > 5 and x < 3) is a contradictory contract: leave it to the fuzzer to report CON004
    return {k: (v[0], v[1]) for k, v in bounds.items() if v != [None, None] and not _crossed(v)}


def _crossed(bound: list[int | None]) -> bool:
    return bound[0] is not None and bound[1] is not None and bound[0] > bound[1]

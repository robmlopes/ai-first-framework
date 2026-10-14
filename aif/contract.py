"""The @contract decorator: precondition, postcondition and declared effects.

Lambdas may name only the parameters they use. In `ensures`, the first
positional parameter receives the function result.
Disable in production with AIF_CONTRACTS=off.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
from collections.abc import Callable
from typing import Any

Predicate = Callable[..., bool]


class ContractViolation(AssertionError):
    """Contract violation carrying a machine-readable counterexample."""

    def __init__(self, kind: str, function: str, counterexample: dict[str, Any]) -> None:
        self.kind = kind
        self.function = function
        self.counterexample = counterexample
        payload = {"kind": kind, "function": function, "counterexample": counterexample}
        super().__init__("AIF_CONTRACT " + json.dumps(payload, default=repr, ensure_ascii=False))


def _call(pred: Predicate, inputs: dict[str, Any], *positional: Any) -> bool:
    params = inspect.signature(pred).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return bool(pred(*positional, **inputs))
    names = list(params)[len(positional) :]
    return bool(pred(*positional, **{k: v for k, v in inputs.items() if k in names}))


def contract(
    *,
    requires: Predicate | None = None,
    ensures: Predicate | None = None,
    effects: list[str] | tuple[str, ...] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(fn)
        name = f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if os.environ.get("AIF_CONTRACTS", "on") == "off":
                return fn(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            inputs = dict(bound.arguments)
            if requires is not None and not _call(requires, inputs):
                raise ContractViolation("precondition", name, {"inputs": inputs})
            result = fn(*args, **kwargs)
            if ensures is not None and not _call(ensures, inputs, result):
                raise ContractViolation("postcondition", name, {"inputs": inputs, "result": result})
            return result

        wrapper.__aif__ = {"effects": list(effects)}  # type: ignore[attr-defined]
        return wrapper

    return decorator

"""AIF012: attribute access must name a real member, for classes (`Cls.x`) and inferred instances (`obj.x`)."""

from __future__ import annotations

import ast
from typing import Any

from aif.model import ClassInfo, FuncInfo, Function, Model, dotted

Error = dict[str, Any]
Env = dict[str, ClassInfo]
_BUILTIN_ATTR_OK = {"__class__", "__dict__", "__doc__", "__name__", "__module__"}


def _error(rel: str, line: int, cause: str, members: set[str]) -> Error:
    return {
        "stage": "lint",
        "rule": "AIF012",
        "file": rel,
        "line": line,
        "cause": cause,
        "suggestion": f"available members: {sorted(m for m in members if not m.startswith('__'))}",
    }


class _Checker:
    def __init__(self, model: Model, module: str, rel: str) -> None:
        self.model, self.module, self.rel = model, module, rel
        self.errors: list[Error] = []

    # ---- type inference -------------------------------------------------------------------
    def type_of(self, expr: ast.expr, env: Env, owner: ClassInfo | None) -> ClassInfo | None:
        """Class of an expression when it is certain: names, `self`, constructors, `self.attr`, `obj.attr`, calls."""
        if isinstance(expr, ast.Name):
            return env.get(expr.id)
        if isinstance(expr, ast.Attribute):
            base = self.type_of(expr.value, env, owner)
            found = self.model.attr_annotation(base, expr.attr) if base else None
            return self.model.resolve_type(found[0].module, found[1]) if found else None
        if isinstance(expr, ast.Call):
            callee = self.model.lookup(self.module, dotted(expr.func)) if dotted(expr.func) else None
            if isinstance(callee, ClassInfo):
                return callee
            if isinstance(callee, FuncInfo):
                return self.model.resolve_type(callee.module, callee.node.returns)
            if isinstance(expr.func, ast.Attribute):
                base = self.type_of(expr.func.value, env, owner)
                method = self.model.find_method(base, expr.func.attr) if base else None
                return self.model.resolve_type(method[0].module, method[1].returns) if method else None
        return None

    def env_for(self, fn: Function, owner: ClassInfo | None) -> Env:
        env: Env = {}
        args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
        for i, a in enumerate(args):
            if i == 0 and owner and not any(dotted(d) in {"staticmethod"} for d in fn.decorator_list):
                if not any(dotted(d) == "classmethod" for d in fn.decorator_list):
                    env[a.arg] = owner
                continue
            hit = self.model.resolve_type(self.module, a.annotation)
            if hit:
                env[a.arg] = hit
        self._assignments(fn, env, owner)
        return env

    def _assignments(self, fn: Function, env: Env, owner: ClassInfo | None) -> None:
        """Local names with exactly one binding whose type is known (re-bound names are dropped)."""
        counts: dict[str, int] = {}
        learned: dict[str, ClassInfo] = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    for name in (x.id for x in ast.walk(t) if isinstance(x, ast.Name)):
                        counts[name] = counts.get(name, 0) + 1
                    if isinstance(t, ast.Name) and (hit := self.type_of(n.value, env, owner)):
                        learned[t.id] = hit
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                counts[n.target.id] = counts.get(n.target.id, 0) + 1
                if hit := self.model.resolve_type(self.module, n.annotation):
                    learned[n.target.id] = hit
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.NamedExpr, ast.AugAssign)):
                for name in (x.id for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)):
                    counts[name] = counts.get(name, 0) + 2
            elif isinstance(n, ast.ExceptHandler) and n.name:
                counts[n.name] = counts.get(n.name, 0) + 2
        params = {a.arg for a in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]}
        for name, cls in learned.items():
            if counts.get(name, 0) == 1 and name not in params:
                env[name] = cls
        for name in list(env):
            if name in params and counts.get(name, 0) > 0:
                del env[name]  # a parameter that is re-bound is no longer trustworthy

    # ---- checks ---------------------------------------------------------------------------
    def check_function(self, fn: Function, owner: ClassInfo | None) -> None:
        env = self.env_for(fn, owner)
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and not (isinstance(n.ctx, ast.Store) and self._is_self(n, fn, owner)):
                self._check_attr(n, env, owner)

    @staticmethod
    def _is_self(n: ast.Attribute, fn: Function, owner: ClassInfo | None) -> bool:
        return bool(owner and fn.args.args and isinstance(n.value, ast.Name) and n.value.id == fn.args.args[0].arg)

    def _check_attr(self, n: ast.Attribute, env: Env, owner: ClassInfo | None) -> None:
        if n.attr in _BUILTIN_ATTR_OK or (n.attr.startswith("__") and n.attr.endswith("__")):
            return
        cls = self.type_of(n.value, env, owner)
        instance = True
        if cls is None and isinstance(n.value, ast.Name) and n.value.id not in env:
            hit = self.model.lookup(self.module, n.value.id)
            if isinstance(hit, ClassInfo):
                cls, instance = hit, False
        if cls is None:
            return
        names = self.model.members(cls, instance)
        if names is not None and n.attr not in names:
            what = f"{n.value.id}.{n.attr}" if isinstance(n.value, ast.Name) else f"{cls.name}.{n.attr}"
            kind = "instance" if instance else "class"
            self.errors.append(_error(self.rel, n.lineno, f"unknown member: {what} ({kind} of {cls.name})", names))

    def check_module_level(self, tree: ast.Module) -> None:
        """Attribute access outside any function body (module statements and class bodies)."""
        skip: set[int] = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                skip |= {id(x) for x in ast.walk(fn)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and id(n) not in skip and not isinstance(n.ctx, ast.Store):
                self._check_attr(n, {}, None)

    def run(self, tree: ast.Module) -> list[Error]:
        self.check_module_level(tree)
        mod = self.model.modules[self.module]
        for fn in mod.functions.values():
            self.check_function(fn.node, None)
        for cls in mod.classes.values():
            for m in cls.methods.values():
                self.check_function(m, cls)
        return self.errors


def check_module(model: Model, module: str, rel: str, tree: ast.Module) -> list[Error]:
    if module not in model.modules:
        return []
    return _Checker(model, module, rel).run(tree)

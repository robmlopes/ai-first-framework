"""Third-party and stdlib import validation without executing any code.

AIF014: the top-level package is neither stdlib, project, the framework, nor declared in `third_party`
        (or it is declared but not installed).
AIF015: `from pkg import name` / `import pkg.sub` names something the installed package does not define.
Namespaces are read from the package source with the AST. Dynamic namespaces are skipped, never guessed.
"""

from __future__ import annotations

import ast
import difflib
import importlib.machinery
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aif.config import Config

Error = dict[str, Any]
FRAMEWORK = {"aif"}
_RUNTIME_ALIASES = {"os.path"}
_SUFFIXES = tuple(importlib.machinery.EXTENSION_SUFFIXES)


def _error(rule: str, file: str, line: int, cause: str, suggestion: str) -> Error:
    return {"stage": "lint", "rule": rule, "file": file, "line": line, "cause": cause, "suggestion": suggestion}


class Resolver:
    def __init__(self, root: Path, cfg: Config) -> None:
        self.root, self.cfg = root, cfg
        self.project = self._project_roots()
        self._located: dict[str, importlib.machinery.ModuleSpec | None] = {}
        self._names: dict[str, set[str] | None] = {}
        self._depth = 0

    def _project_roots(self) -> set[str]:
        out = set(self.cfg.source_dirs)
        for p in self.root.iterdir():
            if p.name.startswith((".", "_")):
                continue
            if (p.is_dir() and any(p.rglob("*.py"))) or (p.suffix == ".py" and p.is_file()):
                out.add(p.stem if p.is_file() else p.name)
        return out

    def classify(self, top: str) -> str:
        if top in self.project:
            return "project"
        if top in FRAMEWORK:
            return "framework"
        if top in sys.stdlib_module_names:
            return "stdlib"
        if top in self.cfg.third_party:
            return "allowed"
        return "unknown"

    # ---- locating without importing ----------------------------------------------------------
    def locate(self, module: str) -> importlib.machinery.ModuleSpec | None:
        if module in self._located:
            return self._located[module]
        parent, _, leaf = module.rpartition(".")
        spec: importlib.machinery.ModuleSpec | None
        if not parent:
            spec = importlib.machinery.PathFinder.find_spec(leaf, sys.path)
            if spec is None and leaf in sys.stdlib_module_names:
                spec = importlib.machinery.BuiltinImporter.find_spec(
                    leaf
                ) or importlib.machinery.FrozenImporter.find_spec(leaf)
        else:
            pspec = self.locate(parent)
            paths = list(pspec.submodule_search_locations or []) if pspec else []
            spec = importlib.machinery.PathFinder.find_spec(module, paths) if paths else None
        self._located[module] = spec
        return spec

    def is_compiled(self, module: str) -> bool:
        spec = self.locate(module)
        return bool(spec and spec.origin and spec.origin.endswith(_SUFFIXES))

    def exists(self, module: str) -> bool:
        return module in _RUNTIME_ALIASES or self.locate(module) is not None

    # ---- namespaces -------------------------------------------------------------------------
    def names(self, module: str) -> set[str] | None:
        """Names importable from `module`, or None when unknown/dynamic."""
        if module not in self._names:
            self._names[module] = self._read(module)
        return self._names[module]

    def _read(self, module: str) -> set[str] | None:
        spec = self.locate(module)
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            return None
        try:
            tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None
        names: set[str] = set()
        if not _collect(tree.body, names, lambda target, level: self._star(module, spec, target, level)):
            return None
        for loc in spec.submodule_search_locations or []:
            names |= _submodules(Path(loc))
        return names

    def _star(
        self, module: str, spec: importlib.machinery.ModuleSpec, target: str | None, level: int
    ) -> set[str] | None:
        """Names brought by `from <target> import *`, only for relative imports inside the same package."""
        if level == 0 or self._depth > 6:
            return None
        base = module.split(".") if spec.submodule_search_locations is not None else module.split(".")[:-1]
        base = base[: len(base) - (level - 1)] if level > 1 else base
        full = ".".join([*base, *([target] if target else [])])
        self._depth += 1
        try:
            return self.names(full)
        finally:
            self._depth -= 1


def _targets(node: ast.expr) -> list[str]:
    return [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]


Star = Callable[[str | None, int], "set[str] | None"]


def _collect(body: list[ast.stmt], names: set[str], star: Star) -> bool:
    """Add top-level names to `names`; False when the namespace is dynamic."""
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name == "__getattr__":
                return False
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                names.update(_targets(t))
                if _touches_globals(t):
                    return False
            if _is_dynamic_value(n.value):
                return False
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            names.update(_targets(n.target))
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                if a.name == "*":
                    got = star(getattr(n, "module", None), getattr(n, "level", 0))
                    if got is None:
                        return False
                    names |= got
                    continue
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith)):
            names.update(_targets(n.target if isinstance(n, (ast.For, ast.AsyncFor)) else n.items[0].context_expr))
            if not _collect(n.body, names, star):
                return False
        elif isinstance(n, (ast.If, ast.While)):
            if not (_collect(n.body, names, star) and _collect(n.orelse, names, star)):
                return False
        elif isinstance(n, ast.Try):
            blocks = [n.body, n.orelse, n.finalbody, *(h.body for h in n.handlers)]
            if not all(_collect(b, names, star) for b in blocks):
                return False
        elif isinstance(n, ast.Expr) and _mutates_globals(n.value):
            return False
    return True


def _is_dynamic_value(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _mutates_globals(node)


def _touches_globals(target: ast.expr) -> bool:
    """`globals()[name] = ...` defines names dynamically."""
    return isinstance(target, ast.Subscript) and _mutates_globals(target.value)


def _mutates_globals(node: ast.expr) -> bool:
    """True when the expression touches the module namespace dynamically (`globals().update(...)`, `setattr(...)`)."""
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"globals", "setattr", "vars"}
        for n in ast.walk(node)
    )


def _submodules(directory: Path) -> set[str]:
    out: set[str] = set()
    if not directory.is_dir():
        return out
    for p in directory.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            out.add(p.name)
        elif p.suffix == ".py":
            out.add(p.stem)
        elif p.name.endswith(_SUFFIXES):
            out.add(p.name.split(".")[0])
    return out


def _is_env_test(test: ast.expr) -> bool:
    """`sys.version_info`/`sys.platform`/`TYPE_CHECKING`/`os.name` conditions: imports under them depend on the host."""
    for n in ast.walk(test):
        if isinstance(n, ast.Attribute) and ast.unparse(n) in {"sys.version_info", "sys.platform", "os.name"}:
            return True
        if isinstance(n, ast.Name) and n.id in {"TYPE_CHECKING", "PY2", "PY3", "WINDOWS", "IS_WINDOWS"}:
            return True
    return False


def _guarded(tree: ast.Module) -> set[int]:
    """ids of statements whose import legitimately depends on the environment.

    Covers `try` blocks catching ImportError (optional dependencies) and `if sys.version_info/platform` branches.
    """
    guarded: set[int] = set()
    for t in ast.walk(tree):
        if isinstance(t, ast.If) and _is_env_test(t.test):
            for stmt in [*t.body, *t.orelse]:
                guarded |= {id(x) for x in ast.walk(stmt)}
    for t in ast.walk(tree):
        if isinstance(t, ast.Try) and any(_catches_import_error(h) for h in t.handlers):
            for stmt in t.body:
                guarded |= {id(x) for x in ast.walk(stmt)}
    return guarded


def _catches_import_error(h: ast.ExceptHandler) -> bool:
    if h.type is None:
        return True
    names = {n.id for n in ast.walk(h.type) if isinstance(n, ast.Name)}
    return bool(names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"})


def check(tree: ast.Module, rel: str, res: Resolver) -> list[Error]:
    cfg = res.cfg
    if not cfg.check_third_party:
        return []
    skip = _guarded(tree)
    errors: list[Error] = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Import):
            for a in node.names:
                errors += _check_module(a.name, node.lineno, rel, res, [])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            errors += _check_module(node.module, node.lineno, rel, res, [a.name for a in node.names])
    return errors


def _check_module(module: str, line: int, rel: str, res: Resolver, wanted: list[str]) -> list[Error]:
    top = module.split(".")[0]
    kind = res.classify(top)
    if kind in {"project", "framework"}:
        return []
    allowed = sorted(res.cfg.third_party)
    if kind == "unknown":
        return [
            _error(
                "AIF014",
                rel,
                line,
                f"unknown package: {top}",
                f"not stdlib, project or declared; declared third-party packages: {allowed}. "
                "If it is a real dependency, add it to pyproject.toml and to `third_party` in aif.toml.",
            )
        ]
    if not res.exists(top):
        if kind == "stdlib":
            return []  # platform-specific stdlib module (msvcrt, _winapi, ...): not importable here, not an error
        return [_error("AIF014", rel, line, f"package '{top}' is declared but not installed", f"pip install {top}")]
    return _check_symbols(module, line, rel, res, wanted)


def _suggest(wanted: str, known: set[str], where: str) -> str:
    close = difflib.get_close_matches(wanted, sorted(known), n=5, cutoff=0.5)
    public = sorted(k for k in known if not k.startswith("_"))
    return f"did you mean {close}?" if close else f"public names in {where}: {public[:40]}"


def _check_symbols(module: str, line: int, rel: str, res: Resolver, wanted: list[str]) -> list[Error]:
    parts = module.split(".")
    for i in range(2, len(parts) + 1):
        sub = ".".join(parts[:i])
        if not res.exists(sub):
            parent = ".".join(parts[: i - 1])
            if res.is_compiled(parent):
                return []  # submodules of a compiled extension cannot be listed without importing it
            known = res.names(parent)
            suggestion = (
                f"available in {parent}: {sorted(known)[:40]}" if known else f"check the {parent} documentation"
            )
            return [_error("AIF015", rel, line, f"unknown module: {sub}", suggestion)]
    known = res.names(module)
    if known is None:
        return []
    missing = [w for w in wanted if w != "*" and w not in known]
    return [_error("AIF015", rel, line, f"unknown name: {module}.{w}", _suggest(w, known, module)) for w in missing]

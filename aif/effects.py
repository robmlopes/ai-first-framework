"""Effect checking: capabilities by signature, layering and direct I/O calls."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from aif.config import Config
from aif.index import source_files

Error = dict[str, Any]
Graph = dict[str, list[tuple[str, int]]]


def _error(rule: str, file: str, line: int, cause: str, suggestion: str) -> Error:
    return {"stage": "effects", "rule": rule, "file": file, "line": line, "cause": cause, "suggestion": suggestion}


def _declared(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str] | None:
    """Effects declared in @contract; None when there is no @contract."""
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "contract":
            for kw in d.keywords:
                if kw.arg == "effects" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    return {e.value for e in kw.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            return set()
    return None


def _type_name(annotation: ast.expr | None) -> str:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value
    return ""


def _check_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel: str, cfg: Config) -> list[Error]:
    declared = _declared(node)
    if declared is None:
        return []
    errors: list[Error] = []
    known = {e for effs in cfg.capabilities.values() for e in effs}
    for e in sorted(declared - known):
        errors.append(
            _error(
                "AIF008", rel, node.lineno, f"unknown effect '{e}' in {node.name}", f"valid effects: {sorted(known)}"
            )
        )
    used: set[str] = set()
    for a in node.args.args + node.args.kwonlyargs:
        used |= set(cfg.capabilities.get(_type_name(a.annotation), []))
    for e in sorted(used - declared):
        errors.append(
            _error(
                "AIF009",
                rel,
                node.lineno,
                f"{node.name} receives a '{e}' capability but does not declare the effect",
                f"add effects=['{e}'] to @contract",
            )
        )
    for e in sorted((declared & known) - used):
        errors.append(
            _error(
                "AIF009",
                rel,
                node.lineno,
                f"{node.name} declares '{e}' without receiving the capability",
                "inject the matching port as a parameter or remove the effect",
            )
        )
    return errors


def _direct_calls(tree: ast.AST, rel: str, cfg: Config) -> list[Error]:
    return [
        _error("AIF010", rel, n.lineno, f"direct effect call: {n.func.id}()", "use an injected port")
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in cfg.forbidden_calls
    ]


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(a.name, n.lineno) for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.append((n.module, n.lineno))
    return out


def _graph(root: Path, cfg: Config) -> Graph:
    g: Graph = {}
    for file in source_files(root, cfg):
        mod = file.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        g[mod] = _imported_modules(ast.parse(file.read_text(encoding="utf-8")))
    return g


def _tainted(mod: str, g: Graph, cfg: Config, seen: set[str]) -> list[str] | None:
    """Import path from `mod` to a forbidden module, if one exists."""
    if mod in seen:
        return None
    seen.add(mod)
    for dep, _ in g.get(mod, []):
        if dep.split(".")[0] in cfg.forbidden_imports:
            return [mod, dep]
        if dep in g and cfg.layer(dep) not in cfg.pure_dirs + cfg.port_dirs:
            return [mod, dep]
        if dep in g:
            sub = _tainted(dep, g, cfg, seen)
            if sub:
                return [mod, *sub]
    return None


def _layers(root: Path, cfg: Config) -> list[Error]:
    g = _graph(root, cfg)
    errors: list[Error] = []
    for mod, deps in g.items():
        if cfg.layer(mod) not in cfg.pure_dirs:
            continue
        rel = mod.replace(".", "/") + ".py"
        for dep, line in deps:
            if dep in g and cfg.layer(dep) not in cfg.pure_dirs + cfg.port_dirs:
                errors.append(
                    _error(
                        "AIF011",
                        rel,
                        line,
                        f"domain imports an effects layer: {dep}",
                        "domain may only depend on domain/ and ports/; invert the dependency",
                    )
                )
            elif dep in g and cfg.layer(dep) in cfg.port_dirs:
                path = _tainted(dep, g, cfg, {mod})
                if path:
                    errors.append(
                        _error(
                            "AIF011",
                            rel,
                            line,
                            "indirect I/O import: " + " -> ".join([mod, *path]),
                            "ports must contain interfaces only",
                        )
                    )
    return errors


def run(root: Path, cfg: Config) -> list[Error]:
    errors: list[Error] = []
    for file in source_files(root, cfg):
        rel = file.relative_to(root).as_posix()
        tree = ast.parse(file.read_text(encoding="utf-8"))
        if cfg.layer(rel) in cfg.pure_dirs:
            errors += _direct_calls(tree, rel, cfg)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                errors += _check_function(node, rel, cfg)
    return errors + _layers(root, cfg)

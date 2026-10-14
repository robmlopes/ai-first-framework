"""AIF rules over the AST. Every error is a structured dict."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from aif import effects
from aif.config import Config
from aif.index import class_attributes, generate, resolve_from, source_files

Error = dict[str, Any]


def _error(rule: str, file: str, line: int, cause: str, suggestion: str) -> Error:
    return {"stage": "lint", "rule": rule, "file": file, "line": line, "cause": cause, "suggestion": suggestion}


def _has_contract(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(d, ast.Call) and getattr(d.func, "id", None) == "contract" for d in node.decorator_list)


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, file: str, cfg: Config, pure: bool, top_level: bool
) -> list[Error]:
    errors: list[Error] = []
    size = (node.end_lineno or node.lineno) - node.lineno + 1
    if size > cfg.max_function_lines:
        errors.append(
            _error(
                "AIF005",
                file,
                node.lineno,
                f"{node.name} has {size} lines (max {cfg.max_function_lines})",
                "split into smaller functions",
            )
        )
    args = [a for a in node.args.args + node.args.kwonlyargs if a.arg not in ("self", "cls")]
    if any(a.annotation is None for a in args) or node.returns is None:
        errors.append(
            _error(
                "AIF003",
                file,
                node.lineno,
                f"{node.name} lacks complete type hints",
                "annotate every parameter and the return type",
            )
        )
    if pure and top_level and not node.name.startswith("_") and not _has_contract(node):
        errors.append(
            _error(
                "AIF002",
                file,
                node.lineno,
                f"public function {node.name} has no @contract",
                "add @contract(requires=..., ensures=..., effects=[])",
            )
        )
    return errors


def _unknown(rule_cause: str, rel: str, node: ast.stmt, suggestion: str) -> Error:
    return _error("AIF006", rel, node.lineno, rule_cause, suggestion)


def _check_project_import(
    node: ast.Import | ast.ImportFrom, rel: str, importer: str, is_pkg: bool, cfg: Config, index: dict[str, Any]
) -> list[Error]:
    """AIF006 for `from x import y` (absolute or relative) and `import x.y` of project modules."""
    errors: list[Error] = []
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.name.split(".")[0] in cfg.source_dirs and a.name not in index:
                errors.append(_unknown(f"unknown module: {a.name}", rel, node, f"existing modules: {sorted(index)}"))
        return errors
    module = resolve_from(importer, is_pkg, node)
    if module is None:
        return [_unknown("relative import goes beyond the project root", rel, node, "use an absolute import")]
    if module.split(".")[0] not in cfg.source_dirs:
        return errors
    if module not in index:
        return [_unknown(f"unknown module: {module}", rel, node, f"existing modules: {sorted(index)}")]
    for a in node.names:
        if a.name not in index[module] and f"{module}.{a.name}" not in index:
            errors.append(
                _unknown(f"unknown symbol: {module}.{a.name}", rel, node, f"available symbols: {sorted(index[module])}")
            )
    return errors


def _check_import(
    node: ast.Import | ast.ImportFrom, rel: str, cfg: Config, pure: bool, index: dict[str, Any]
) -> list[Error]:
    importer = rel.removesuffix(".py").replace("/", ".")
    is_pkg = importer.endswith(".__init__")
    importer = importer.removesuffix(".__init__")
    errors: list[Error] = []
    mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
    for m in mods:
        if pure and m.split(".")[0] in cfg.forbidden_imports:
            errors.append(
                _error(
                    "AIF001",
                    rel,
                    node.lineno,
                    f"forbidden import in pure module: {m}",
                    "receive the effect through an injected port (ports/)",
                )
            )
    return errors + _check_project_import(node, rel, importer, is_pkg, cfg, index)


def _known_classes(tree: ast.Module, index: dict[str, Any], cfg: Config) -> dict[str, dict[str, Any]]:
    """Map local names bound to project classes (defined here or imported) to their index entries."""
    classes: dict[str, dict[str, Any]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in index and node.level == 0:
            for a in node.names:
                entry = index[node.module].get(a.name)
                if entry and entry["kind"] == "class":
                    classes[a.asname or a.name] = entry
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = {"methods": {m: {} for m in _method_names(node)}, "attributes": class_attributes(node)}
    return classes


def _method_names(node: ast.ClassDef) -> list[str]:
    return [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _check_members(tree: ast.Module, rel: str, index: dict[str, Any], cfg: Config) -> list[Error]:
    """AIF012: `Class.member` must name an existing method or class attribute."""
    classes = _known_classes(tree, index, cfg)
    shadowed = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    errors: list[Error] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        entry = classes.get(node.value.id)
        if entry is None or node.value.id in shadowed or node.attr.startswith("__"):
            continue
        members = {*entry["methods"], *entry["attributes"]}
        if node.attr not in members:
            errors.append(
                _error(
                    "AIF012",
                    rel,
                    node.lineno,
                    f"unknown member: {node.value.id}.{node.attr}",
                    f"available members: {sorted(members)}",
                )
            )
    return errors


def _check_file(root: Path, file: Path, cfg: Config, index: dict[str, Any]) -> list[Error]:
    rel = file.relative_to(root).as_posix()
    text = file.read_text(encoding="utf-8")
    tree = ast.parse(text)
    pure = cfg.layer(rel) in cfg.pure_dirs
    errors: list[Error] = []
    n = len(text.splitlines())
    if n > cfg.max_file_lines:
        errors.append(_error("AIF005", rel, 1, f"file has {n} lines (max {cfg.max_file_lines})", "split the module"))
    errors += _check_members(tree, rel, index, cfg)
    top = {id(f) for f in tree.body}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors += _check_function(node, rel, cfg, pure, id(node) in top)
        elif isinstance(node, ast.Global):
            errors.append(_error("AIF007", rel, node.lineno, "use of 'global'", "pass state as a parameter"))
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None or getattr(node.type, "id", "") in ("Exception", "BaseException"):
                errors.append(_error("AIF004", rel, node.lineno, "generic except", "catch a specific typed error"))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            errors += _check_import(node, rel, cfg, pure, index)
    return errors


def run(root: Path, cfg: Config) -> list[Error]:
    index = generate(root, cfg)
    errors: list[Error] = []
    for file in source_files(root, cfg):
        errors += _check_file(root, file, cfg, index)
    return errors + effects.run(root, cfg)

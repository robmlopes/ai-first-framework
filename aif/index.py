"""Generates .aif/index.json: the map the AI consults instead of guessing names."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from aif.config import Config


def _contract(deco: ast.expr) -> dict[str, Any] | None:
    if isinstance(deco, ast.Call) and getattr(deco.func, "id", None) == "contract":
        return {kw.arg: ast.unparse(kw.value) for kw in deco.keywords if kw.arg}
    return None


def _function(node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str = "function") -> dict[str, Any]:
    params = [a for a in node.args.args if not (kind == "method" and a.arg in ("self", "cls"))]
    args = [f"{a.arg}: {ast.unparse(a.annotation) if a.annotation else '?'}" for a in params]
    contract = next((c for d in node.decorator_list if (c := _contract(d))), None)
    doc = (ast.get_docstring(node) or "").split("\n")[0]
    return {
        "kind": kind,
        "args": args,
        "returns": ast.unparse(node.returns) if node.returns else "?",
        "contract": contract,
        "doc": doc,
        "line": node.lineno,
    }


def class_attributes(node: ast.ClassDef) -> list[str]:
    """Class-level names that are not methods: annotated fields, assignments, nested classes."""
    names: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            names.append(item.target.id)
        elif isinstance(item, ast.Assign):
            names += [t.id for t in item.targets if isinstance(t, ast.Name)]
        elif isinstance(item, ast.ClassDef):
            names.append(item.name)
    return names


def _class(node: ast.ClassDef) -> dict[str, Any]:
    methods = {
        m.name: _function(m, "method") for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return {
        "kind": "class",
        "line": node.lineno,
        "doc": (ast.get_docstring(node) or "").split("\n")[0],
        "methods": methods,
        "attributes": class_attributes(node),
    }


def source_files(root: Path, cfg: Config) -> list[Path]:
    return sorted(p for d in cfg.source_dirs for p in (root / d).rglob("*.py"))


def module_of(root: Path, file: Path) -> str:
    rel = file.relative_to(root).with_suffix("")
    return ".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)


def generate(root: Path, cfg: Config) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for file in source_files(root, cfg):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        symbols: dict[str, Any] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols[node.name] = _function(node)
            elif isinstance(node, ast.ClassDef):
                symbols[node.name] = _class(node)
        index[module_of(root, file)] = symbols
    return index


def save(root: Path, cfg: Config) -> dict[str, Any]:
    index = generate(root, cfg)
    target = root / ".aif" / "index.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return index

"""Effect checking: capabilities by signature, layering and direct I/O calls."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from aif import dynamic
from aif.config import Config
from aif.index import module_of, resolve_from, source_files

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


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted origin, from imports and simple module-level aliases (`X = Y`, `type X = Y`)."""
    out: dict[str, str] = {}
    for n in tree.body:
        if isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            for a in n.names:
                out[a.asname or a.name] = f"{n.module}.{a.name}"
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            ref = _dotted(n.value)
            if ref:
                out[n.targets[0].id] = ref
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None:
            ref = _dotted(n.value)
            if ref:
                out[n.target.id] = ref
        elif isinstance(n, ast.TypeAlias):
            ref = _dotted(n.value)
            if ref and isinstance(n.name, ast.Name):
                out[n.name.id] = ref
    return out


def _dotted(node: ast.expr) -> str:
    """`a.b.c` for a Name/Attribute chain, else ''."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _resolve(name: str, aliases: dict[str, str]) -> str:
    """Expand the first segment of a dotted name through the alias table (cycle-safe)."""
    seen: set[str] = set()
    while True:
        head, _, rest = name.partition(".")
        if head not in aliases or head in seen:
            return name
        seen.add(head)
        name = aliases[head] + ("." + rest if rest else "")


def _annotation_types(annotation: ast.expr | None, aliases: dict[str, str]) -> set[str]:
    """Every type name mentioned in an annotation (unions, generics, quoted forms), alias-resolved."""
    if annotation is None:
        return set()
    names: set[str] = set()
    for n in ast.walk(annotation):
        if isinstance(n, (ast.Name, ast.Attribute)):
            full = _resolve(_dotted(n), aliases)
            names |= {full, full.rpartition(".")[2]}
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            try:
                names |= _annotation_types(ast.parse(n.value, mode="eval").body, aliases)
            except SyntaxError:
                names.add(n.value)
    return names


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, rel: str, cfg: Config, aliases: dict[str, str]
) -> list[Error]:
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
        for t in _annotation_types(a.annotation, aliases):
            used |= set(cfg.capabilities.get(t, []))
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


def _direct_calls(tree: ast.Module, rel: str, cfg: Config) -> list[Error]:
    """AIF010/AIF013 for pure modules: calls, references and dynamic dispatch of effects."""
    aliases = _aliases(tree)
    errors: list[Error] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            full = _resolve(_dotted(n.func), aliases)
            if full and dynamic.is_banned(full, cfg):
                errors.append(_error("AIF010", rel, n.lineno, f"direct effect call: {full}()", "use an injected port"))
    errors += dynamic.banned_references(tree, rel, cfg, _resolve, _dotted, aliases)
    return errors + dynamic.dynamic_calls(tree, rel)


def _imported_modules(tree: ast.AST, importer: str, is_pkg: bool) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(a.name, n.lineno) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            module = resolve_from(importer, is_pkg, n)
            if module:
                out.append((module, n.lineno))
                out += [(f"{module}.{a.name}", n.lineno) for a in n.names]
    return out


def _graph(root: Path, cfg: Config) -> Graph:
    g: Graph = {}
    for file in source_files(root, cfg):
        mod = module_of(root, file)
        g[mod] = _imported_modules(ast.parse(file.read_text(encoding="utf-8")), mod, file.name == "__init__.py")
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
        aliases = _aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                errors += _check_function(node, rel, cfg, aliases)
    return errors + _layers(root, cfg)

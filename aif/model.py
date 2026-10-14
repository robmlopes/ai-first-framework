"""Project model: classes, functions, imports and type resolution, built once per run from the AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from aif.config import Config
from aif.index import class_attributes, module_of, resolve_from, source_files

Function = ast.FunctionDef | ast.AsyncFunctionDef
TRANSPARENT_BASES = {"object", "Protocol", "typing.Protocol", "Generic", "typing.Generic", "ABC", "abc.ABC"}
TRANSPARENT_DECORATORS = {"dataclass", "dataclasses.dataclass", "final", "typing.final", "runtime_checkable"}
_MAX_DEPTH = 8


def dotted(node: ast.expr) -> str:
    """`a.b.c` for a Name/Attribute chain, else ''."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


@dataclass
class FuncInfo:
    module: str
    name: str
    node: Function


@dataclass
class ClassInfo:
    module: str
    name: str
    node: ast.ClassDef
    methods: dict[str, Function] = field(default_factory=dict)
    class_names: set[str] = field(default_factory=set)
    instance_names: set[str] = field(default_factory=set)
    attr_types: dict[str, ast.expr] = field(default_factory=dict)
    opaque: bool = False


def _self_name(fn: Function) -> str | None:
    decos = {dotted(d) for d in fn.decorator_list}
    if "staticmethod" in decos or not fn.args.args:
        return None
    return fn.args.args[0].arg


def _own(fn: Function) -> list[ast.AST]:
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(fn.body)
    while stack:
        n = stack.pop()
        out.append(n)
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))
    return out


def _build_class(module: str, node: ast.ClassDef) -> ClassInfo:
    info = ClassInfo(module, node.name, node)
    info.class_names = set(class_attributes(node))
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            info.attr_types[item.target.id] = item.annotation
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.methods[item.name] = item
            self_arg = _self_name(item)
            for n in _own(item) if self_arg else []:
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == self_arg:
                    if isinstance(n.ctx, ast.Store):
                        info.instance_names.add(n.attr)
                    elif n.attr == "__dict__":
                        info.opaque = True
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Attribute):
                    info.attr_types[n.target.attr] = n.annotation
                if isinstance(n, ast.Call) and dotted(n.func) == "setattr":
                    info.opaque = True
    decorators = {dotted(d.func if isinstance(d, ast.Call) else d) for d in node.decorator_list}
    dynamic = {"__getattr__", "__getattribute__", "__slots__"} & (info.class_names | set(info.methods))
    info.opaque = info.opaque or bool(decorators - TRANSPARENT_DECORATORS) or bool(node.keywords) or bool(dynamic)
    return info


@dataclass
class Module:
    name: str
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    functions: dict[str, FuncInfo] = field(default_factory=dict)
    imports: dict[str, str] = field(default_factory=dict)


class Model:
    def __init__(self, root: Path, cfg: Config) -> None:
        self.modules: dict[str, Module] = {}
        for file in source_files(root, cfg):
            name = module_of(root, file)
            self.modules[name] = self._scan(name, file.name == "__init__.py", ast.parse(file.read_text("utf-8")))

    @staticmethod
    def _scan(name: str, is_pkg: bool, tree: ast.Module) -> Module:
        mod = Module(name)
        stack: list[ast.stmt] = list(tree.body)
        while stack:
            n = stack.pop(0)
            if isinstance(n, ast.ClassDef):
                mod.classes[n.name] = _build_class(name, n)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                mod.functions[n.name] = FuncInfo(name, n.name, n)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    mod.imports[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom):
                base = resolve_from(name, is_pkg, n)
                for a in n.names if base else []:
                    mod.imports[a.asname or a.name] = f"{base}.{a.name}"
            elif isinstance(n, (ast.If, ast.Try)):
                stack += n.body + n.orelse
        return mod

    def lookup(self, module: str, name: str, depth: int = 0) -> ClassInfo | FuncInfo | None:
        """Resolve a (possibly dotted) name as seen from `module` to a project class or function."""
        mod = self.modules.get(module)
        if mod is None or depth > _MAX_DEPTH:
            return None
        head, _, rest = name.partition(".")
        if not rest:
            if head in mod.classes:
                return mod.classes[head]
            if head in mod.functions:
                return mod.functions[head]
        if head not in mod.imports:
            return None
        full = mod.imports[head] + ("." + rest if rest else "")
        parts = full.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            target = ".".join(parts[:cut])
            if target in self.modules and cut == len(parts) - 1:
                return self.lookup(target, parts[-1], depth + 1)
        return None

    def resolve_type(self, module: str, annotation: ast.expr | None, depth: int = 0) -> ClassInfo | None:
        """The single project class an annotation denotes (through Optional/unions/quotes); else None."""
        if annotation is None or depth > _MAX_DEPTH:
            return None
        found: dict[tuple[str, str], ClassInfo] = {}
        for n in ast.walk(annotation):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                try:
                    inner = self.resolve_type(module, ast.parse(n.value, mode="eval").body, depth + 1)
                except SyntaxError:
                    inner = None
                if inner:
                    found[(inner.module, inner.name)] = inner
            elif isinstance(n, (ast.Name, ast.Attribute)) and dotted(n):
                hit = self.lookup(module, dotted(n))
                if isinstance(hit, ClassInfo):
                    found[(hit.module, hit.name)] = hit
        if isinstance(annotation, ast.Subscript) and dotted(annotation.value).rpartition(".")[2] not in {
            "Optional",
            "Union",
        }:
            return None  # list[X], dict[...], Callable[...]: the container is not X
        return next(iter(found.values())) if len(found) == 1 else None

    def mro(self, cls: ClassInfo) -> list[ClassInfo] | None:
        """The class followed by its project bases; None when any base is not understood."""
        out = [cls]
        for base in cls.node.bases:
            name = dotted(base.value if isinstance(base, ast.Subscript) else base)
            if name in TRANSPARENT_BASES:
                continue
            parent = self.lookup(cls.module, name)
            if not isinstance(parent, ClassInfo) or parent in out:
                return None
            chain = self.mro(parent)
            if chain is None:
                return None
            out += chain
        return out

    def members(self, cls: ClassInfo, instance: bool) -> set[str] | None:
        chain = self.mro(cls)
        if chain is None or any(c.opaque for c in chain):
            return None
        names: set[str] = set()
        for c in chain:
            names |= c.class_names | set(c.methods)
            if instance:
                names |= c.instance_names
        return names

    def find_method(self, cls: ClassInfo, name: str) -> tuple[ClassInfo, Function] | None:
        for c in self.mro(cls) or [cls]:
            if name in c.methods:
                return c, c.methods[name]
        return None

    def attr_annotation(self, cls: ClassInfo, name: str) -> tuple[ClassInfo, ast.expr] | None:
        for c in self.mro(cls) or [cls]:
            if name in c.attr_types:
                return c, c.attr_types[name]
        return None

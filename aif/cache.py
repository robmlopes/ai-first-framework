"""Fuzz result cache: a module is skipped when it and everything it imports are unchanged.

The key of a module hashes its source, the source of every project module it imports (transitively), the
fuzz settings, the `fuzz_setup` module and the framework's own fuzz code, so a stale hit is not possible
unless something outside the project (a third-party upgrade) changes behaviour.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aif.config import Config
from aif.effects import graph
from aif.index import module_of, source_files

_FRAMEWORK = ("fuzz.py", "bounds.py", "contract.py")


def _file_of(root: Path, module: str) -> Path | None:
    base = root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _closure(module: str, g: dict[str, list[tuple[str, int]]]) -> set[str]:
    seen: set[str] = set()
    todo = [module]
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        todo += [dep for dep, _ in g.get(current, []) if dep in g]
    return seen


def _digest(parts: list[bytes]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(hashlib.sha256(part).digest())
    return h.hexdigest()


def keys(root: Path, cfg: Config) -> dict[str, str]:
    """Cache key per source module."""
    g = graph(root, cfg)
    here = Path(__file__).resolve().parent
    settings = json.dumps([cfg.fuzz_examples, cfg.fuzz_finite_numbers, cfg.fuzz_setup]).encode()
    setup = _file_of(root, cfg.fuzz_setup) if cfg.fuzz_setup else None
    common = [settings, *[(here / n).read_bytes() for n in _FRAMEWORK], setup.read_bytes() if setup else b""]
    out: dict[str, str] = {}
    for file in source_files(root, cfg):
        module = module_of(root, file)
        parts = [common[0]] + common[1:]
        for dep in sorted(_closure(module, g)):
            path = _file_of(root, dep)
            parts.append(dep.encode() + (path.read_bytes() if path else b""))
        out[module] = _digest(parts)
    return out


def _store(root: Path) -> Path:
    return root / ".aif" / "cache" / "fuzz.json"


def load(root: Path) -> dict[str, str]:
    try:
        data = json.loads(_store(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(root: Path, passed: dict[str, str]) -> None:
    target = _store(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(passed, indent=1, sort_keys=True), encoding="utf-8")

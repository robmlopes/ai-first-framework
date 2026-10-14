"""Fixtures: throwaway AIF projects built in tmp_path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from aif.config import Config, load

AIF_TOML = """[aif]
source_dirs = ["domain", "ports", "adapters"]
pure_dirs = ["domain"]
port_dirs = ["ports"]
max_file_lines = 200
max_function_lines = 40
forbidden_imports = ["os", "sqlite3", "requests"]
forbidden_calls = ["open", "print"]

[aif.capabilities]
DbWrite = ["db.write"]
"""

PORT = """from typing import Protocol


class DbWrite(Protocol):
    def save(self, value: int) -> None: ...
"""


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    @property
    def cfg(self) -> Config:
        return load(self.root)

    def rules(self, errors: list[dict]) -> list[str]:
        return sorted(e["rule"] for e in errors if "rule" in e)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    p = Project(tmp_path)
    p.write("aif.toml", AIF_TOML)
    for d in ("domain", "ports", "adapters"):
        p.write(f"{d}/__init__.py", "")
    p.write("ports/db.py", PORT)
    return p


@pytest.fixture
def make() -> Callable[[Path], Project]:
    return Project

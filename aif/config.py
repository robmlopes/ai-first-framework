from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    source_dirs: list[str] = field(default_factory=lambda: ["domain"])
    pure_dirs: list[str] = field(default_factory=lambda: ["domain"])
    max_file_lines: int = 200
    max_function_lines: int = 40
    intents: bool = True
    style: bool = True
    typecheck: bool = True
    typecheck_tests: bool = True
    mypy_args: list[str] = field(default_factory=lambda: ["--strict"])
    forbidden_imports: list[str] = field(default_factory=list)
    port_dirs: list[str] = field(default_factory=lambda: ["ports"])
    forbidden_calls: list[str] = field(
        default_factory=lambda: [
            "open",
            "print",
            "input",
            "exec",
            "eval",
            "compile",
            "__import__",
            "getattr",
            "setattr",
        ]
    )
    capabilities: dict[str, list[str]] = field(default_factory=dict)

    def layer(self, path: str) -> str:
        return path.replace(".", "/").split("/")[0]


def load(root: Path) -> Config:
    file = root / "aif.toml"
    if not file.exists():
        return Config()
    data = tomllib.loads(file.read_text(encoding="utf-8")).get("aif", {})
    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})

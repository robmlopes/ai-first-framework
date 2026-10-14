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
    limits: dict[str, dict[str, int]] = field(default_factory=dict)  # per-layer overrides: [aif.limits.web]
    count_code_lines: bool = True  # AIF005 ignores blank lines, comments and docstrings
    limit_warn_ratio: float = 0.9  # warn when a function or file reaches this share of its limit
    entry_dirs: list[str] = field(default_factory=list)  # web / CLI layers; added to source_dirs
    adapter_dirs: list[str] = field(default_factory=lambda: ["adapters"])
    composition_roots: list[str] = field(default_factory=list)  # modules allowed to import adapters from entry_dirs
    parallel: bool = True  # run mypy, fuzz and pytest concurrently
    docs_check: bool = True  # `aif check` also verifies that docs/ agrees with the code (DOC001-DOC004)
    history: bool = True  # append every `aif check` to .aif/history.jsonl
    intents: bool = True
    style: bool = True
    typecheck: bool = True
    typecheck_tests: bool = True
    fuzz: bool = True
    fuzz_examples: int = 100
    fuzz_finite_numbers: bool = True
    fuzz_setup: str = ""
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
    forbidden_clock: list[str] = field(
        default_factory=lambda: [
            "datetime.datetime.now",
            "datetime.datetime.utcnow",
            "datetime.datetime.today",
            "datetime.date.today",
            "time.time",
            "time.time_ns",
            "time.monotonic",
            "time.perf_counter",
            "time.sleep",
        ]
    )
    third_party: list[str] = field(default_factory=list)
    check_third_party: bool = True
    capabilities: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_dirs = [*self.source_dirs, *(d for d in self.entry_dirs if d not in self.source_dirs)]

    def limit(self, path: str, key: str) -> int:
        """Size limit for `path`: the layer override from `limits` when present, else the global value."""
        value = self.limits.get(self.layer(path), {}).get(key)
        return value if value is not None else int(getattr(self, key))

    def layer(self, path: str) -> str:
        return path.replace(".", "/").split("/")[0]


def load(root: Path) -> Config:
    file = root / "aif.toml"
    if not file.exists():
        return Config()
    data = tomllib.loads(file.read_text(encoding="utf-8")).get("aif", {})
    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})

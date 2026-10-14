"""Style stage: ruff format (canonical form) and ruff check, as structured errors."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from aif.config import Config

Error = dict[str, Any]


def _targets(root: Path, cfg: Config) -> list[str]:
    return [d for d in [*cfg.source_dirs, "tests"] if (root / d).is_dir()]


def _ruff(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ruff", *args], cwd=root, capture_output=True, text=True)


def _unavailable(proc: subprocess.CompletedProcess[str]) -> list[Error]:
    return [
        {
            "stage": "style",
            "rule": "ruff",
            "file": "",
            "line": 0,
            "cause": "ruff did not run",
            "suggestion": "pip install ruff",
            "detail": (proc.stdout + proc.stderr)[-800:],
        }
    ]


def run(root: Path, cfg: Config) -> list[Error]:
    if not cfg.style:
        return []
    targets = _targets(root, cfg)
    errors: list[Error] = []
    for name, args in (("format", ("format", "--check")), ("check", ("check",))):
        proc = _ruff(root, *args, "--output-format=json", *targets)
        if proc.returncode not in (0, 1):
            return _unavailable(proc)
        for d in json.loads(proc.stdout or "[]"):
            rel = Path(d["filename"]).resolve().relative_to(root).as_posix()
            code = "format" if name == "format" else d["code"]
            cause = "file is not in canonical format" if name == "format" else d["message"]
            fixable = name == "format" or d.get("fix")
            errors.append(
                {
                    "stage": "style",
                    "rule": code,
                    "file": rel,
                    "line": d["location"]["row"],
                    "cause": cause,
                    "suggestion": "run `python -m aif fix`" if fixable else "fix manually",
                }
            )
    return errors


def fix(root: Path, cfg: Config) -> Error:
    """Apply canonical formatting and safe autofixes; return what remains."""
    targets = _targets(root, cfg)
    _ruff(root, "check", "--fix", "--quiet", *targets)
    _ruff(root, "format", "--quiet", *targets)
    remaining = run(root, cfg)
    return {"ok": not remaining, "errors": remaining}

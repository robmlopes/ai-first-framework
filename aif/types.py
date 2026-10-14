"""Type-check stage: runs mypy over source_dirs (and tests/) and returns structured errors."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import aif
from aif.config import Config

Error = dict[str, Any]
_LINE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?:(?P<col>\d+):)? (?P<sev>error|note): (?P<msg>.*?)(?:  \[(?P<code>[\w-]+)\])?$"
)


_HINTS = {
    "return-value": (
        "returned value does not match the declared type; "
        "for an adapter, check it implements every port method with the same signature"
    ),
    "arg-type": "argument type does not match the parameter; check the port Protocol signature",
    "assignment": "assigned value does not match the declared type",
    "attr-defined": "attribute does not exist; check .aif/index.json and the Protocol definition",
    "name-defined": "name is not defined or not imported; check .aif/index.json",
    "import-not-found": "module not found; check .aif/index.json for module paths",
    "no-untyped-def": "annotate every parameter and the return type",
}


def _parse(output: str) -> list[Error]:
    errors: list[Error] = []
    for raw in output.splitlines():
        m = _LINE.match(raw)
        if m is None:
            continue
        if m["sev"] == "note":
            continue
        if m["sev"] == "error":
            errors.append(
                {
                    "stage": "types",
                    "rule": m["code"] or "mypy",
                    "file": m["file"].replace("\\", "/"),
                    "line": int(m["line"]),
                    "cause": m["msg"],
                    "suggestion": _HINTS.get(m["code"] or "", ""),
                }
            )
    return errors


def _framework_path() -> list[str]:
    """Directory that makes `aif` importable for mypy when it runs from a source checkout.

    When `aif` is installed (site-packages/dist-packages) mypy already finds it, and mypy refuses a
    MYPYPATH that points into site-packages, so nothing is added in that case.
    """
    parent = Path(aif.__file__).resolve().parent.parent
    return [] if parent.name in {"site-packages", "dist-packages"} else [str(parent)]


def run(root: Path, cfg: Config) -> list[Error]:
    if not cfg.typecheck:
        return []
    dirs = [d for d in [*cfg.source_dirs, *(["tests"] if cfg.typecheck_tests else [])] if (root / d).is_dir()]
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        *cfg.mypy_args,
        "--no-error-summary",
        "--show-error-codes",
        "--no-pretty",
        "--no-color-output",
        *dirs,
    ]
    env = {
        **os.environ,
        "MYPYPATH": os.pathsep.join(filter(None, [*_framework_path(), os.environ.get("MYPYPATH", "")])),
    }
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env)
    errors = _parse(proc.stdout)
    if proc.returncode not in (0, 1) or (proc.returncode == 1 and not errors):
        return [
            {
                "stage": "types",
                "rule": "mypy",
                "file": "",
                "line": 0,
                "cause": "mypy did not run",
                "suggestion": "pip install mypy",
                "detail": (proc.stdout + proc.stderr)[-800:],
            }
        ]
    return errors

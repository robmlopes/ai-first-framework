"""Run in the project's own virtual environment.

The `aif` command is often installed outside the project (pipx, system Python). Its stages shell out to mypy, ruff and
pytest and resolve third-party imports, so they must see the project's dependencies. Otherwise AIF014 reports every
declared package as "not installed" although the code is fine. When the project has a `.venv`, `aif` re-runs itself
with that interpreter.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import aif

VENV_NAMES = (".venv", "venv")
# commands that execute or analyze project code and therefore need the project's dependencies
NEEDS_PROJECT_ENV = frozenset({"check", "fix", "fuzz", "index", "patch"})
GUARD = "AIF_IN_PROJECT_ENV"


def project_python(root: Path) -> Path | None:
    """The interpreter of the project's virtual environment, if it has one."""
    for name in VENV_NAMES:
        for rel in ("bin/python", "Scripts/python.exe"):
            candidate = root / name / rel
            if candidate.is_file():
                return candidate
    return None


def _same_env(python: Path) -> bool:
    return Path(sys.prefix).resolve() == python.parent.parent.resolve()


def foreign_interpreter(root: Path) -> Path | None:
    """The project's interpreter when the current process is running under a different one."""
    python = project_python(root)
    return python if python is not None and not _same_env(python) else None


def _framework_env(python: Path) -> dict[str, str] | None:
    """Environment under which `python` can import aif, or None when it cannot."""
    base = dict(os.environ)
    if subprocess.run([str(python), "-c", "import aif"], capture_output=True, env=base).returncode == 0:
        return base
    parent = Path(aif.__file__).resolve().parent.parent
    if parent.name in {"site-packages", "dist-packages"}:
        return None  # aif is a regular installed package; exposing its whole site-packages would shadow the venv
    return {**base, "PYTHONPATH": os.pathsep.join(filter(None, [str(parent), base.get("PYTHONPATH", "")]))}


def reexec(root: Path, command: str | None, argv: list[str]) -> int | None:
    """Re-run `aif argv` under the project's interpreter and return its exit code; None means "run here"."""
    if command not in NEEDS_PROJECT_ENV or os.environ.get(GUARD):
        return None
    python = foreign_interpreter(root)
    if python is None:
        return None
    env = _framework_env(python)
    if env is None:
        return None
    env[GUARD] = "1"
    return subprocess.run([str(python), "-m", "aif", *argv], env=env).returncode


def hint(root: Path) -> str:
    """Extra advice for "not installed" errors when aif is running outside the project's environment."""
    python = foreign_interpreter(root)
    if python is None:
        return ""
    return (
        f" Note: aif is running under {sys.executable}, not the project's environment ({python}); "
        f"install aif there (`{python} -m pip install aif-starter`) or run `{python} -m aif check`."
    )

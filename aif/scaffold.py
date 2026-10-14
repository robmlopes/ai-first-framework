"""`aif init`: create a new AIF project that passes `aif check` from the first commit.

Templates live in `aif/templates/` as plain files so they stay readable and are not duplicated as Python strings.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from aif import agents

TEMPLATES = Path(__file__).resolve().parent / "templates"
HOOKS = ("pre-commit", "commit-msg")

# project path -> template file
LAYOUT = {
    "aif.toml": "aif.toml",
    "pyproject.toml": "pyproject.toml",
    ".gitignore": "gitignore",
    ".aif/protocol.md": "protocol.md",
    ".aif/intents/bootstrap.md": "bootstrap-intent.md",
    "tests/strategies.py": "strategies.py.txt",
    "ports/clock.py": "clock.py.txt",
    "scripts/pre-commit": "pre-commit",
    "scripts/commit-msg": "commit-msg",
}
EMPTY = ("domain/__init__.py", "ports/__init__.py", "adapters/__init__.py", "tests/__init__.py")


def template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _files(project_name: str) -> dict[str, str]:
    files = {rel: template(src) for rel, src in LAYOUT.items()}
    files["pyproject.toml"] = files["pyproject.toml"].replace("{name}", project_name)
    files.update({rel: "" for rel in EMPTY})
    return files


def _git(root: Path, *args: str) -> bool:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False).returncode == 0
    except FileNotFoundError:
        return False


def _install_hooks(root: Path) -> bool:
    if not (root / ".git").exists():
        return False
    for hook in HOOKS:
        target = root / ".git" / "hooks" / hook
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template(hook), encoding="utf-8")
        target.chmod(0o755)
    return True


def init(root: Path, git: bool = True) -> dict[str, Any]:
    """Create the project skeleton in `root`. Refuses to overwrite an existing AIF project."""
    if (root / "aif.toml").exists():
        return {
            "ok": False,
            "stage": "init",
            "cause": f"{root} already has an aif.toml",
            "suggestion": "use `aif check`",
        }
    root.mkdir(parents=True, exist_ok=True)
    name = root.name.lower().replace("_", "-").replace(" ", "-") or "aif-project"
    written: list[str] = []
    for rel, text in _files(name).items():
        path = root / rel
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if rel.startswith("scripts/"):
            path.chmod(0o755)
        written.append(rel)
    written += agents.write(root)
    if git and not (root / ".git").exists():
        _git(root, "init", "-q", "-b", "main")
    return {
        "ok": True,
        "root": str(root),
        "written": sorted(written),
        "git_hooks_installed": _install_hooks(root) if git else False,
        "next": ["pip install -e '.[dev]'", "aif check --json", "aif intent new <id> <title>"],
    }

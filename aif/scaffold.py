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
# profile -> everything it adds to the base project
PROFILES: dict[str, dict[str, Any]] = {
    "web-api": {
        "layer": "web",
        "config": "web-api.toml",
        "dev": ["fastapi", "httpx"],
        "files": {"web/main.py": "web-api-main.py.txt", "tests/test_web.py": "web-api-test.py.txt"},
        "scope": ["web/main.py"],
    },
    "cli": {
        "layer": "cli",
        "config": "cli.toml",
        "dev": [],
        "files": {"cli/main.py": "cli-main.py.txt", "tests/test_cli.py": "cli-test.py.txt"},
        "scope": ["cli/main.py"],
    },
}
EMPTY = ("domain/__init__.py", "ports/__init__.py", "adapters/__init__.py", "tests/__init__.py")


def template(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _apply_profile(files: dict[str, str], profile: str) -> None:
    """Merge a profile (entry layer, dependencies, starter files) into the base project files."""
    spec = PROFILES[profile]
    layer = spec["layer"]
    keys, _, tables = template(f"profiles/{spec['config']}").partition("# --tables--\n")
    base = files["aif.toml"]
    for line in keys.splitlines():  # a profile key replaces the base line of the same name instead of duplicating it
        name = line.split("=", 1)[0].strip()
        if name and not line.startswith("#"):
            base = "".join(ln for ln in base.splitlines(True) if not ln.startswith(f"{name} ="))
    files["aif.toml"] = base.replace("[aif]\n", "[aif]\n" + keys, 1).rstrip("\n") + "\n" + tables
    deps = ", ".join(f'"{d}"' for d in spec["dev"])
    files["pyproject.toml"] = files["pyproject.toml"].replace(
        '"ruff"]', '"ruff"' + (f", {deps}" if deps else "") + "]", 1
    )
    files["pyproject.toml"] = files["pyproject.toml"].replace('"adapters*"]', f'"adapters*", "{layer}*"]', 1)
    files[f"{layer}/__init__.py"] = ""
    files.update({rel: template(f"profiles/{src}") for rel, src in spec["files"].items()})
    scope = "".join(f"- {rel}\n" for rel in spec["scope"])
    files[".aif/intents/bootstrap.md"] = files[".aif/intents/bootstrap.md"].replace(
        "- aif.toml\n", "- aif.toml\n" + scope, 1
    )


def _files(project_name: str, profile: str | None = None) -> dict[str, str]:
    files = {rel: template(src) for rel, src in LAYOUT.items()}
    files["pyproject.toml"] = files["pyproject.toml"].replace("{name}", project_name)
    files.update({rel: "" for rel in EMPTY})
    if profile:
        _apply_profile(files, profile)
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


def init(root: Path, git: bool = True, profile: str | None = None) -> dict[str, Any]:
    """Create the project skeleton in `root`. Refuses to overwrite an existing AIF project."""
    if (root / "aif.toml").exists():
        return {
            "ok": False,
            "stage": "init",
            "cause": f"{root} already has an aif.toml",
            "suggestion": "use `aif check`",
        }
    if profile is not None and profile not in PROFILES:
        return {
            "ok": False,
            "stage": "init",
            "cause": f"unknown profile: {profile}",
            "suggestion": f"available profiles: {sorted(PROFILES)}",
        }
    root.mkdir(parents=True, exist_ok=True)
    name = root.name.lower().replace("_", "-").replace(" ", "-") or "aif-project"
    written: list[str] = []
    for rel, text in _files(name, profile).items():
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
        "profile": profile,
        "next": ["pip install -e '.[dev]'", "aif check --json", "aif intent new <id> <title>"],
    }

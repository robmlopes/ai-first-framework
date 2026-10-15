"""`aif upgrade`: bring a project's AIF-owned files up to date with the installed framework.

Framework-owned files are replaced: the numbered protocol rules, the agent files, the hooks and the `.gitignore`
entries. Yours are kept: any `## ` section you added to `.aif/protocol.md`, and `aif.toml`, to which only new options
are added with their defaults. Anything that needs a decision is only reported under `manual`.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from aif import agents, scaffold

# (key, why) for values that older templates generated and that the framework no longer recommends
_STALE_ENTRIES = {
    "forbidden_imports": ("datetime", "date/time types are allowed now; only clock reads are banned (forbidden_clock)"),
}


def _template_defaults() -> dict[str, Any]:
    section: dict[str, Any] = tomllib.loads(scaffold.template("aif.toml")).get("aif", {})
    return section


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(_format(v) for v in value) + "]"
    return str(value)


def missing_options(root: Path) -> dict[str, Any]:
    """Options the current template defines that the project's aif.toml does not set."""
    current = tomllib.loads((root / "aif.toml").read_text(encoding="utf-8")).get("aif", {})
    return {k: v for k, v in _template_defaults().items() if k not in current and not isinstance(v, dict)}


def manual_review(root: Path) -> list[str]:
    current = tomllib.loads((root / "aif.toml").read_text(encoding="utf-8")).get("aif", {})
    notes = []
    for key, (entry, why) in _STALE_ENTRIES.items():
        if entry in current.get(key, []):
            notes.append(f"aif.toml: `{key}` still contains '{entry}': {why}. Remove it if you want the new behavior.")
    return notes


def _gitignore_missing(root: Path) -> list[str]:
    wanted = [ln for ln in scaffold.template("gitignore").splitlines() if ln.strip()]
    path = root / ".gitignore"
    have = set(path.read_text(encoding="utf-8").splitlines()) if path.is_file() else set()
    return [ln for ln in wanted if ln not in have]


def _split_protocol(text: str) -> tuple[str, str]:
    """(framework part, project sections): everything from the first `## ` heading on belongs to the project."""
    match = re.search(r"^## ", text, flags=re.M)
    return (text[: match.start()], text[match.start() :]) if match else (text, "")


def _merged_protocol(root: Path) -> str:
    """The current framework protocol followed by the project's own `## ` sections, which are never discarded."""
    path = root / ".aif" / "protocol.md"
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    _, own = _split_protocol(current)
    base = scaffold.template("protocol.md")
    return base.rstrip("\n") + "\n\n" + own if own else base


def _protocol_stale(root: Path) -> bool:
    path = root / ".aif" / "protocol.md"
    return not path.is_file() or path.read_text(encoding="utf-8") != _merged_protocol(root)


def _hooks_stale(root: Path) -> list[str]:
    if not (root / ".git").is_dir():
        return []
    return [
        h
        for h in scaffold.HOOKS
        if not (root / ".git" / "hooks" / h).is_file()
        or (root / ".git" / "hooks" / h).read_text(encoding="utf-8") != scaffold.template(h)
    ]


def _add_options(root: Path, options: dict[str, Any]) -> None:
    path = root / "aif.toml"
    text = path.read_text(encoding="utf-8")
    block = "# added by `aif upgrade`\n" + "".join(f"{k} = {_format(v)}\n" for k, v in options.items())
    path.write_text(re.sub(r"^\[aif\]\n", lambda m: m.group(0) + block, text, count=1, flags=re.M), encoding="utf-8")


def run(root: Path, apply: bool = False) -> dict[str, Any]:
    """Report what is out of date; with `apply`, update it."""
    if not (root / "aif.toml").is_file():
        return {"ok": False, "stage": "upgrade", "cause": f"{root} has no aif.toml", "suggestion": "use `aif init`"}
    options = missing_options(root)
    plan: dict[str, Any] = {
        "protocol": _protocol_stale(root),
        "agent_files": agents.stale(root),
        "hooks": _hooks_stale(root),
        "gitignore": _gitignore_missing(root),
        "config_added": options,
    }
    if apply:
        _apply(root, plan)
    pending = any(bool(v) for v in plan.values())
    return {
        "ok": True,
        "applied": apply,
        "up_to_date": not pending,
        "changes": plan,
        "manual": manual_review(root),
        "next": ["aif check --json"] if apply and pending else ([] if not pending else ["aif upgrade --apply"]),
    }


def _apply(root: Path, plan: dict[str, Any]) -> None:
    if plan["protocol"]:
        target = root / ".aif" / "protocol.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_merged_protocol(root), encoding="utf-8")
    if plan["config_added"]:
        _add_options(root, plan["config_added"])
    if plan["gitignore"]:
        path = root / ".gitignore"
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        path.write_text(
            old.rstrip("\n") + ("\n" if old else "") + "\n".join(plan["gitignore"]) + "\n", encoding="utf-8"
        )
    agents.write(root)
    if plan["hooks"]:
        scaffold._install_hooks(root)  # noqa: SLF001 - same package, shared helper

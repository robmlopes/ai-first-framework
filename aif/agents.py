"""Agent instruction files, generated from the single source `.aif/protocol.md`."""

from __future__ import annotations

from pathlib import Path

TARGETS: dict[str, tuple[str, str]] = {
    "AGENTS.md": ("# Agent instructions (AIF)\n\nFor any coding agent working in this repository.\n\n", ""),
    "CLAUDE.md": ("# Agent protocol (AIF)\n\n", ""),
    ".cursor/rules/aif.mdc": (
        "---\ndescription: AIF agent protocol\nalwaysApply: true\n---\n\n# Agent protocol (AIF)\n\n",
        "",
    ),
}
NOTICE = "<!-- Generated from .aif/protocol.md by `aif agents`. Do not edit by hand. -->\n\n"


def render(root: Path) -> dict[str, str]:
    body = (root / ".aif" / "protocol.md").read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for name, (head, tail) in TARGETS.items():
        # front matter must stay first in .mdc files
        if head.startswith("---"):
            front, _, rest = head.partition("\n\n# ")
            out[name] = front + "\n\n" + NOTICE + "# " + rest + body + tail
        else:
            title, _, rest = head.partition("\n\n")
            out[name] = title + "\n\n" + NOTICE + rest + body + tail
    return out


def stale(root: Path) -> list[str]:
    """Generated files that are missing or differ from the canonical protocol."""
    return [
        name
        for name, text in render(root).items()
        if not (root / name).is_file() or (root / name).read_text(encoding="utf-8") != text
    ]


def write(root: Path) -> list[str]:
    written: list[str] = []
    for name, text in render(root).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        written.append(name)
    return written

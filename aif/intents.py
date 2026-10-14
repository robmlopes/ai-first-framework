"""Intents: the human "why" per feature, stored in .aif/intents/<id>.md and validated by `aif check`.

Format (Markdown):

    # <title>

    ## Why
    <non-empty text>

    ## Scope
    - domain/transfer.py
    - ports/db.py

    ## Acceptance
    - <non-empty bullet list>
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aif.config import Config

Error = dict[str, Any]
SECTIONS = ("Why", "Scope", "Acceptance")
_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TEMPLATE = """# {title}

## Why
Explain, in a sentence or two, the human reason for this feature.

## Scope
- {example}

## Acceptance
- Describe one observable behaviour that must hold.
"""


def _dir(root: Path) -> Path:
    return root / ".aif" / "intents"


def _error(rule: str, file: str, cause: str, suggestion: str) -> Error:
    return {"stage": "intents", "rule": rule, "file": file, "line": 1, "cause": cause, "suggestion": suggestion}


def parse(text: str) -> dict[str, Any]:
    """Return {'title': str, 'sections': {name: [non-empty lines]}}."""
    title = ""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    return {"title": title, "sections": sections}


def scope_paths(parsed: dict[str, Any]) -> list[str]:
    return [
        line.removeprefix("- ").strip().strip("`")
        for line in parsed["sections"].get("Scope", [])
        if line.startswith("- ")
    ]


def _validate(root: Path, file: Path) -> list[Error]:
    rel = file.relative_to(root).as_posix()
    errors: list[Error] = []
    if not _ID.match(file.stem):
        errors.append(
            _error("INT001", rel, f"intent id '{file.stem}' is not kebab-case", "use lowercase-words-with-dashes.md")
        )
    parsed = parse(file.read_text(encoding="utf-8"))
    if not parsed["title"]:
        errors.append(_error("INT002", rel, "missing '# title' line", "start the file with '# <title>'"))
    for name in SECTIONS:
        if not parsed["sections"].get(name):
            errors.append(_error("INT002", rel, f"section '## {name}' is missing or empty", f"fill in '## {name}'"))
    for path in scope_paths(parsed):
        if not (root / path).is_file():
            errors.append(
                _error(
                    "INT003",
                    rel,
                    f"scope path does not exist: {path}",
                    "update the intent or restore the file (see .aif/index.json)",
                )
            )
    return errors


def run(root: Path, cfg: Config) -> list[Error]:
    if not cfg.intents or not _dir(root).is_dir():
        return []
    errors: list[Error] = []
    for file in sorted(_dir(root).glob("*.md")):
        errors += _validate(root, file)
    return errors


def listing(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for file in sorted(_dir(root).glob("*.md")) if _dir(root).is_dir() else []:
        parsed = parse(file.read_text(encoding="utf-8"))
        out.append({"id": file.stem, "title": parsed["title"], "scope": scope_paths(parsed)})
    return out


def create(root: Path, cfg: Config, intent_id: str, title: str) -> dict[str, Any]:
    if not _ID.match(intent_id):
        return {"ok": False, "stage": "intents", "cause": f"invalid id '{intent_id}'", "suggestion": "use kebab-case"}
    target = _dir(root) / f"{intent_id}.md"
    if target.exists():
        return {
            "ok": False,
            "stage": "intents",
            "cause": f"{intent_id} already exists",
            "suggestion": "edit it instead",
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    example = f"{cfg.source_dirs[0]}/<module>.py"
    target.write_text(_TEMPLATE.format(title=title, example=example), encoding="utf-8")
    return {"ok": True, "file": target.relative_to(root).as_posix()}


def check_message(root: Path, message: str) -> Error | None:
    """A commit message must carry an 'Intent: <id>' trailer naming an existing intent."""
    m = re.search(r"^Intent:\s*(\S+)\s*$", message, re.MULTILINE)
    if m is None:
        return _error(
            "INT004",
            "<commit-message>",
            "commit message has no 'Intent: <id>' trailer",
            "add a line 'Intent: <id>' (see `aif intent list`)",
        )
    if not (_dir(root) / f"{m.group(1)}.md").is_file():
        return _error(
            "INT005",
            "<commit-message>",
            f"unknown intent '{m.group(1)}'",
            f"existing intents: {[i['id'] for i in listing(root)]}",
        )
    return None


def intent_id_of(message: str) -> str | None:
    m = re.search(r"^Intent:\s*(\S+)\s*$", message, re.MULTILINE)
    return m.group(1) if m else None


def check_scope(root: Path, message: str, changed: list[str]) -> list[Error]:
    """INT006: every changed source file must be listed in the cited intent's Scope.

    Always allowed: intent files, docs, tests, root-level metadata and empty package markers (`__init__.py`).
    """
    intent = intent_id_of(message)
    file = _dir(root) / f"{intent}.md"
    if intent is None or not file.is_file():
        return []
    scope = set(scope_paths(parse(file.read_text(encoding="utf-8"))))
    errors: list[Error] = []
    for path in changed:
        if path in scope or path.startswith((".aif/", "docs/", "tests/")) or "/" not in path:
            continue
        if path.endswith("/__init__.py") and not (root / path).read_text(encoding="utf-8").strip():
            continue
        errors.append(
            _error(
                "INT006",
                path,
                f"{path} changed but is not in the Scope of intent '{intent}'",
                f"add it to '## Scope' in .aif/intents/{intent}.md or split the commit",
            )
        )
    return errors

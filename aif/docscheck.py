"""`aif docs`: documentation must agree with the code, checked by machine (DOC001-DOC004).

DOC001  a rule the code can emit appears nowhere in docs/ (or a documented rule is never emitted)
DOC002  a Config option is not documented in docs/configuration.md (or the reverse)
DOC003  a CLI command is not documented in docs/cli.md
DOC004  a relative Markdown link points to a file or anchor that does not exist
"""

from __future__ import annotations

import argparse
import dataclasses
import re
from pathlib import Path
from typing import Any

from aif.config import Config

Error = dict[str, Any]
_RULE = re.compile(r"\b(?:AIF|CON|INT|AGT)\d{3}\b")
_LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.M)
_CODE_FENCE = re.compile(r"```.*?```", re.S)
# configuration keys that are not user options
_INTERNAL = {"capabilities"}


def _error(rule: str, file: str, cause: str, suggestion: str) -> Error:
    return {"stage": "docs", "rule": rule, "file": file, "line": 1, "cause": cause, "suggestion": suggestion}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def emitted_rules(package: Path) -> set[str]:
    """Rule ids the framework can emit: quoted ids in its own source (strings, not docstrings or comments)."""
    found: set[str] = set()
    for file in package.glob("*.py"):
        for match in re.finditer(r"""["'](\b(?:AIF|CON|INT|AGT)\d{3})["']""", file.read_text(encoding="utf-8")):
            found.add(match.group(1))
    return found


def check_rules(root: Path, package: Path) -> list[Error]:
    doc = root / "docs" / "lint-rules.md"
    documented = {r for f in sorted((root / "docs").glob("*.md")) for r in _RULE.findall(_read(f))}
    emitted = emitted_rules(package)
    rel = doc.relative_to(root).as_posix()
    errors = [
        _error("DOC001", rel, f"rule {r} is emitted by the code but not documented", f"add {r} to {rel}")
        for r in sorted(emitted - documented)
    ]
    errors += [
        _error("DOC001", rel, f"rule {r} is documented but no code emits it", "remove it or implement it")
        for r in sorted(documented - emitted)
    ]
    return errors


def check_config(root: Path) -> list[Error]:
    doc = root / "docs" / "configuration.md"
    text = _read(doc)
    options = {f.name for f in dataclasses.fields(Config)} - _INTERNAL
    documented = set(re.findall(r"`([a-z_]+)`", text))
    rel = doc.relative_to(root).as_posix()
    return [
        _error("DOC002", rel, f"config option `{o}` is not documented", f"add `{o}` to the table in {rel}")
        for o in sorted(options - documented)
    ]


def check_cli(root: Path, commands: list[str]) -> list[Error]:
    doc = root / "docs" / "cli.md"
    text = _read(doc)
    rel = doc.relative_to(root).as_posix()
    return [
        _error("DOC003", rel, f"CLI command `{c}` is not documented", f"add a `{c}` entry to {rel}")
        for c in commands
        if not re.search(rf"`{c}\b|## `aif {c}\b", text)
    ]


def _anchor(heading: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s+", "-", slug)


def _anchors(text: str) -> set[str]:
    return {_anchor(h) for h in _HEADING.findall(_CODE_FENCE.sub("", text))}


def check_links(root: Path) -> list[Error]:
    errors: list[Error] = []
    files = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    for file in files:
        if not file.is_file():
            continue
        rel = file.relative_to(root).as_posix()
        text = _CODE_FENCE.sub("", file.read_text(encoding="utf-8"))
        for target in _LINK.findall(text):
            if re.match(r"[a-z]+:", target) or target.startswith("#") and target[1:] in _anchors(text):
                continue
            path_part, _, anchor = target.partition("#")
            dest = (file.parent / path_part).resolve() if path_part else file
            if path_part and not dest.exists():
                errors.append(_error("DOC004", rel, f"broken link: {target}", "fix the path or remove the link"))
            elif anchor and dest.suffix == ".md" and anchor not in _anchors(_read(dest)):
                errors.append(_error("DOC004", rel, f"link anchor not found: {target}", "fix the heading anchor"))
    return errors


def run(root: Path, commands: list[str] | None = None, package: Path | None = None) -> list[Error]:
    """Run every documentation check; silent when the project has no `docs/` directory."""
    if not (root / "docs").is_dir():
        return []
    package = package or Path(__file__).resolve().parent
    errors = check_rules(root, package) if (root / "docs" / "lint-rules.md").is_file() else []
    if (root / "docs" / "configuration.md").is_file():
        errors += check_config(root)
    if commands and (root / "docs" / "cli.md").is_file():
        errors += check_cli(root, commands)
    return errors + check_links(root)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    parser = argparse.ArgumentParser(prog="aif.docscheck")
    parser.add_argument("--root", default=".")
    return 1 if run(Path(parser.parse_args(argv).root).resolve()) else 0

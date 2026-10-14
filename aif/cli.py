"""aif check [--json] | aif index"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from aif import index, intents, lint, patch, style, types
from aif.config import load

_CONTRACT = re.compile(r"AIF_CONTRACT (\{.*\})")


def _tests(root: Path) -> list[dict[str, Any]]:
    if not (root / "tests").exists():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "r.xml"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if not xml.exists():
            return [{"stage": "tests", "cause": "pytest did not run", "detail": (proc.stdout + proc.stderr)[-800:]}]
        errors: list[dict[str, Any]] = []
        for case in ET.parse(xml).getroot().iter("testcase"):
            failure = case.find("failure")
            failure = failure if failure is not None else case.find("error")
            if failure is None:
                continue
            text = (failure.get("message") or "") + "\n" + (failure.text or "")
            found = _CONTRACT.search(text)
            error: dict[str, Any] = {"stage": "tests", "test": f"{case.get('classname')}::{case.get('name')}"}
            if found:
                error["cause"] = "contract violated"
                error.update(json.loads(found.group(1)))
            else:
                error["cause"] = (failure.get("message") or "failure")[:300]
            errors.append(error)
        return errors


def check(root: Path) -> dict[str, Any]:
    cfg = load(root)
    index.save(root, cfg)
    errors = style.run(root, cfg)
    if not errors:
        errors = intents.run(root, cfg)
    if not errors:
        errors = lint.run(root, cfg)
    if not errors:
        errors = types.run(root, cfg)
    if not errors:  # tests only run when lint and types pass
        errors = _tests(root)
    return {"ok": not errors, "errors": errors}


def _staged_files(root: Path) -> list[str]:
    """Paths staged for the current commit; empty when not in a git repository."""
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=root, capture_output=True, text=True
    )
    return proc.stdout.split() if proc.returncode == 0 else []


def _intent(root: Path, action: str | None, arg: str | None, rest: list[str]) -> int:
    """aif intent new ID TITLE... | list | commit-msg FILE"""
    cfg = load(root)
    if action == "new" and arg:
        out: Any = intents.create(root, cfg, arg, " ".join(rest) or arg.replace("-", " ").capitalize())
    elif action == "list":
        out = {"ok": True, "intents": intents.listing(root)}
    elif action == "commit-msg" and arg:
        message = Path(arg).read_text(encoding="utf-8")
        err = intents.check_message(root, message)
        errs = [err] if err else intents.check_scope(root, message, _staged_files(root))
        out = {"ok": not errs, "errors": errs}
    else:
        print("usage: aif intent new ID [TITLE...] | list | commit-msg FILE", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aif")
    p.add_argument("command", choices=["check", "index", "patch", "fix", "intent"])
    p.add_argument("file", nargs="?", help="patch: target file, e.g. domain/transfer.py")
    p.add_argument("symbol", nargs="?", help="patch: top-level function or class to replace")
    p.add_argument("rest", nargs="*", help="intent: extra words (title for `new`)")
    p.add_argument("--from", dest="source", help="patch: file with the new definition (default: stdin)")
    p.add_argument("--dry-run", action="store_true", help="patch: show the diff without writing")
    p.add_argument("--keep", action="store_true", help="patch: keep the change even if lint fails")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root", default=".")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    if a.command == "index":
        index.save(root, load(root))
        print("index written to .aif/index.json")
        return 0
    if a.command == "intent":
        return _intent(root, a.file, a.symbol, a.rest)
    if a.command == "fix":
        out = style.fix(root, load(root))
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if out["ok"] else 1
    if a.command == "patch":
        if not a.file or not a.symbol:
            p.error("patch requires FILE and SYMBOL")
        new = Path(a.source).read_text(encoding="utf-8") if a.source else sys.stdin.read()
        out = patch.apply(root, load(root), a.file, a.symbol, new, a.dry_run, a.keep)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=repr))
        return 0 if out["ok"] else 1
    r = check(root)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=repr))
    else:
        print("OK" if r["ok"] else f"{len(r['errors'])} error(s)")
        for e in r["errors"]:
            print(" -", e.get("rule", e["stage"]), e.get("file", e.get("test", "")), e["cause"])
    return 0 if r["ok"] else 1

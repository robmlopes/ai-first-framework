"""aif check [--json] | aif index"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aif import agents, docscheck, env, fuzz, history, index, intents, patch, pipeline, scaffold, style, upgrade
from aif.config import load

check = pipeline.check


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


def _background(root: Path, changed: bool) -> int:
    """Start `aif check --json` detached; results land in `.aif/last-check.json` (see `aif status`)."""
    history.write_last(root, {"status": "running", "started": time.time()})
    cmd = [sys.executable, "-m", "aif", "check", "--json", "--root", str(root), *(["--changed"] if changed else [])]
    subprocess.Popen(cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print(json.dumps({"status": "running", "poll": "aif status", "result": ".aif/last-check.json"}))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aif")
    p.add_argument(
        "command",
        choices=[
            "check",
            "index",
            "patch",
            "fix",
            "intent",
            "agents",
            "fuzz",
            "init",
            "status",
            "stats",
            "docs",
            "upgrade",
        ],
    )
    p.add_argument("file", nargs="?", help="patch: target file, e.g. domain/transfer.py; init: target directory")
    p.add_argument("symbol", nargs="?", help="patch: top-level function or class to replace")
    p.add_argument("rest", nargs="*", help="intent: extra words (title for `new`)")
    p.add_argument("--from", dest="source", help="patch: file with the new definition (default: stdin)")
    p.add_argument("--dry-run", action="store_true", help="patch: show the diff without writing")
    p.add_argument("--keep", action="store_true", help="patch: keep the change even if lint fails")
    p.add_argument("--no-git", action="store_true", help="init: do not run git init or install hooks")
    p.add_argument("--changed", action="store_true", help="check: style and lint only files changed since HEAD")
    p.add_argument("--apply", action="store_true", help="upgrade: write the changes (default: only report them)")
    p.add_argument("--profile", help="init: add an entry layer and starter files (web-api, cli)")
    p.add_argument("--report", action="store_true", help="fuzz: list what was tested and what was skipped, and why")
    p.add_argument("--background", action="store_true", help="check: start detached, poll with `aif status`")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root", default=".")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    rerun = env.reexec(root, a.command, sys.argv[1:] if argv is None else argv)
    if rerun is not None:
        return rerun
    if a.command == "upgrade":
        out = upgrade.run(root, apply=a.apply)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if out["ok"] else 1
    if a.command == "init":
        out = scaffold.init(Path(a.file or a.root).resolve(), git=not a.no_git, profile=a.profile)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if out["ok"] else 1
    if a.command == "status":
        out = history.read_last(root)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=repr))
        return 0 if out.get("status") == "done" and out.get("ok") else (3 if out.get("status") == "running" else 1)
    if a.command == "docs":
        errs = docscheck.run(root, pipeline.COMMANDS)
        print(json.dumps({"ok": not errs, "errors": errs}, indent=2, ensure_ascii=False))
        return 0 if not errs else 1
    if a.command == "stats":
        print(json.dumps(history.stats(root), indent=2, ensure_ascii=False))
        return 0
    if a.command == "fuzz":
        if a.report:
            full = fuzz.report(root, load(root))
            print(json.dumps(full, indent=2, ensure_ascii=False, default=repr))
            return 0 if full["ok"] else 1
        errors = fuzz.run(root, load(root))
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2, ensure_ascii=False, default=repr))
        return 0 if not errors else 1
    if a.command == "index":
        index.save(root, load(root))
        print("index written to .aif/index.json")
        return 0
    if a.command == "agents":
        names = agents.write(root)
        print(json.dumps({"ok": True, "written": names}, indent=2))
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
    if a.background:
        return _background(root, a.changed)
    r = check(root, a.changed)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=repr))
    else:
        print("OK" if r["ok"] else f"{len(r['errors'])} error(s)", f"({r['timings']['total']}s)")
        for e in r["errors"]:
            print(" -", e.get("rule", e["stage"]), e.get("file", e.get("test", "")), e["cause"])
        for w in r["warnings"]:
            print(" ~", w["rule"], w["file"], w["cause"])
    return 0 if r["ok"] else 1

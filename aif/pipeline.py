"""The `aif check` pipeline: ordered stages, optional changed-only mode, parallel heavy stages, timings."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from aif import agents, docscheck, fuzz, history, index, intents, limits, lint, style, types
from aif.config import Config, load

Error = dict[str, Any]
COMMANDS = ["check", "index", "patch", "fix", "intent", "agents", "fuzz", "init", "status", "stats", "docs", "upgrade"]
_CONTRACT = re.compile(r"AIF_CONTRACT (\{.*\})")


def tests(root: Path) -> list[Error]:
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
        errors: list[Error] = []
        for case in ET.parse(xml).getroot().iter("testcase"):
            failure = case.find("failure")
            failure = failure if failure is not None else case.find("error")
            if failure is None:
                continue
            text = (failure.get("message") or "") + "\n" + (failure.text or "")
            found = _CONTRACT.search(text)
            error: Error = {"stage": "tests", "test": f"{case.get('classname')}::{case.get('name')}"}
            if found:
                error["cause"] = "contract violated"
                error.update(json.loads(found.group(1)))
            else:
                error["cause"] = (failure.get("message") or "failure")[:300]
            errors.append(error)
        return errors


def agent_files(root: Path) -> list[Error]:
    if not (root / ".aif" / "protocol.md").is_file():
        return []
    return [
        {
            "stage": "agents",
            "rule": "AGT001",
            "file": name,
            "line": 1,
            "cause": "agent instruction file is out of date with .aif/protocol.md",
            "suggestion": "run `aif agents`",
        }
        for name in agents.stale(root)
    ]


def changed_files(root: Path) -> frozenset[str] | None:
    """Files modified, staged or untracked relative to HEAD; None outside a git repository."""
    probes = (
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    found: set[str] = set()
    for cmd in probes:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        if proc.returncode != 0:
            if cmd[1] == "diff":  # no commits yet: everything tracked counts as changed
                tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
                if tracked.returncode != 0:
                    return None
                found.update(tracked.stdout.split())
                continue
            return None
        found.update(proc.stdout.split())
    return frozenset(found)


def _timed(name: str, fn: Callable[[], list[Error]], timings: dict[str, float]) -> list[Error]:
    start = time.perf_counter()
    try:
        return fn()
    finally:
        timings[name] = round(time.perf_counter() - start, 2)


def _light(root: Path, cfg: Config, only: frozenset[str] | None, timings: dict[str, float]) -> list[Error]:
    """Fast, ordered stages: each runs only when the previous one is clean."""
    for name, fn in (
        ("style", lambda: style.run(root, cfg, only)),
        ("agents", lambda: agent_files(root)),
        ("intents", lambda: intents.run(root, cfg)),
        ("docs", lambda: docscheck.run(root, COMMANDS) if cfg.docs_check else []),
        ("lint", lambda: lint.run(root, cfg, only)),
    ):
        errors = _timed(name, fn, timings)
        if errors:
            return errors
    return []


def _heavy(root: Path, cfg: Config, timings: dict[str, float]) -> list[Error]:
    """mypy, fuzz and pytest are independent processes; run them together, report in pipeline order."""
    stages: list[tuple[str, Callable[[], list[Error]]]] = [
        ("types", lambda: types.run(root, cfg)),
        ("fuzz", lambda: fuzz.run(root, cfg, use_cache=True)),
        ("tests", lambda: tests(root)),
    ]
    if not cfg.parallel:
        for name, fn in stages:
            errors = _timed(name, fn, timings)
            if errors:
                return errors
        return []
    with ThreadPoolExecutor(max_workers=len(stages)) as pool:
        futures = [(name, pool.submit(_timed, name, fn, timings)) for name, fn in stages]
        results = [f.result() for _, f in futures]
    return next((r for r in results if r), [])


def check(root: Path, changed: bool = False) -> dict[str, Any]:
    """Run the pipeline. With `changed`, style and lint look only at files that differ from HEAD."""
    started = time.perf_counter()
    cfg = load(root)
    timings: dict[str, float] = {}
    only = changed_files(root) if changed else None
    _timed("index", lambda: (index.save(root, cfg), [])[1], timings)
    errors = _light(root, cfg, only, timings) or _heavy(root, cfg, timings)
    result: dict[str, Any] = {
        "ok": not errors,
        "errors": errors,
        "warnings": limits.warnings(root, cfg, only),
        "timings": {**timings, "total": round(time.perf_counter() - started, 2)},
    }
    if changed:
        result["changed_only"] = sorted(only) if only is not None else "not a git repository: checked everything"
    if cfg.history:
        history.record(root, result, changed)
    history.write_last(root, {"status": "done", **result})
    return result

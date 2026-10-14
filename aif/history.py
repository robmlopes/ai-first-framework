"""Run history and the last-check snapshot: measured data about how the framework is used."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

HISTORY = "history.jsonl"
LAST = "last-check.json"


def _dir(root: Path) -> Path:
    path = root / ".aif"
    path.mkdir(exist_ok=True)
    return path


def write_last(root: Path, payload: dict[str, Any]) -> None:
    """Atomically replace `.aif/last-check.json` so a poller never reads half a file."""
    target = _dir(root) / LAST
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=repr), encoding="utf-8")
    tmp.replace(target)


def read_last(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / ".aif" / LAST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "none", "cause": "no check has run yet", "suggestion": "run `aif check --json`"}
    return data if isinstance(data, dict) else {"status": "none"}


def record(root: Path, result: dict[str, Any], changed: bool) -> None:
    """Append one line per `aif check`: outcome, rules that fired, stage timings."""
    errors = result.get("errors", [])
    line = {
        "ts": round(time.time(), 3),
        "ok": result.get("ok", False),
        "changed_only": changed,
        "errors": len(errors),
        "stages": sorted({e.get("stage", "?") for e in errors}),
        "rules": dict(Counter(e.get("rule") or e.get("stage", "?") for e in errors)),
        "timings": result.get("timings", {}),
    }
    with (_dir(root) / HISTORY).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def load(root: Path) -> list[dict[str, Any]]:
    path = root / ".aif" / HISTORY
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _attempts(runs: list[dict[str, Any]]) -> list[int]:
    """Failing runs before each success: 0 means the first check already passed."""
    counts: list[int] = []
    failed = 0
    for run in runs:
        if run.get("ok"):
            counts.append(failed)
            failed = 0
        else:
            failed += 1
    return counts


def stats(root: Path) -> dict[str, Any]:
    runs = load(root)
    if not runs:
        return {"runs": 0, "cause": "no history yet", "suggestion": "run `aif check` first"}
    rules: Counter[str] = Counter()
    stage_time: dict[str, list[float]] = {}
    for run in runs:
        rules.update(run.get("rules", {}))
        for stage, secs in run.get("timings", {}).items():
            if stage == "total":
                continue
            stage_time.setdefault(stage, []).append(float(secs))
    attempts = _attempts(runs)
    total = [float(r.get("timings", {}).get("total", 0.0)) for r in runs]
    return {
        "runs": len(runs),
        "passed": sum(1 for r in runs if r.get("ok")),
        "failed": sum(1 for r in runs if not r.get("ok")),
        "pending_failures_since_last_ok": next((i for i, r in enumerate(reversed(runs)) if r.get("ok")), len(runs)),
        "attempts_before_ok": {
            "samples": len(attempts),
            "average": round(sum(attempts) / len(attempts), 2) if attempts else None,
            "max": max(attempts) if attempts else None,
        },
        "average_seconds": round(sum(total) / len(total), 2),
        "average_seconds_per_stage": {k: round(sum(v) / len(v), 2) for k, v in sorted(stage_time.items())},
        "top_rules": rules.most_common(10),
    }

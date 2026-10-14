from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from aif import cache, cli, fuzz, history, pipeline
from aif.config import Config
from tests.framework.conftest import Project

GOOD = (
    "from aif import contract\n\n\n"
    "@contract(requires=lambda x: x >= 0, ensures=lambda r, x: r >= x)\n"
    "def f(x: int) -> int:\n    return x + 1\n"
)


def git(project: Project, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=t", *args], cwd=project.root, check=True, capture_output=True
    )


def test_timings_cover_every_stage(project: Project) -> None:
    project.write("domain/m.py", GOOD)
    out = pipeline.check(project.root)
    assert out["ok"] and {"index", "style", "lint", "types", "fuzz", "tests", "total"} <= set(out["timings"]) | {
        "tests"
    }
    assert out["timings"]["total"] >= 0


def test_changed_mode_ignores_unchanged_files(project: Project) -> None:
    project.write("domain/m.py", GOOD)
    project.write("adapters/old.py", "def old( ) -> int :\n  return 1\n")  # badly formatted, but committed
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "base")
    project.write("domain/n.py", GOOD.replace("def f", "def g"))
    out = pipeline.check(project.root, changed=True)
    assert out["changed_only"] == ["domain/n.py"]
    assert not [e for e in out["errors"] if e.get("file") == "adapters/old.py"]


def test_changed_mode_reports_changed_file_errors(project: Project) -> None:
    project.write("domain/m.py", GOOD)
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "base")
    project.write("domain/m.py", "import os\n\n" + GOOD)
    out = pipeline.check(project.root, changed=True)
    assert not out["ok"] and out["errors"][0]["file"] == "domain/m.py"


def test_changed_mode_outside_git_checks_everything(project: Project) -> None:
    project.write("domain/m.py", GOOD)
    out = pipeline.check(project.root, changed=True)
    assert out["ok"] and "not a git repository" in out["changed_only"]


def test_fuzz_cache_skips_unchanged_modules(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    project.write("domain/m.py", GOOD)
    assert fuzz.run(project.root, project.cfg, use_cache=True) == []
    calls: list[list[str]] = []

    def spy(root: Path, cfg: Config, modules: list[str]) -> list[dict[str, Any]]:
        calls.append(modules)
        return []

    monkeypatch.setattr(fuzz, "_run_worker", spy)
    fuzz.run(project.root, project.cfg, use_cache=True)
    assert calls == []  # nothing changed: worker not started


def test_fuzz_cache_invalidated_by_change_and_by_dependency(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    project.write("domain/base.py", "VALUE = 1\n")
    project.write("domain/m.py", "from domain.base import VALUE\n\n" + GOOD)
    fuzz.run(project.root, project.cfg, use_cache=True)
    seen: list[list[str]] = []

    def spy(root: Path, cfg: Config, modules: list[str]) -> list[dict[str, Any]]:
        seen.append(sorted(modules))
        return []

    monkeypatch.setattr(fuzz, "_run_worker", spy)
    project.write("domain/base.py", "VALUE = 2\n")
    fuzz.run(project.root, project.cfg, use_cache=True)
    assert seen == [["domain.base", "domain.m"]]  # the dependent module is re-fuzzed too


def test_failing_module_is_never_cached(project: Project) -> None:
    bad = GOOD.replace("x + 1", "x - 1")
    project.write("domain/m.py", bad)
    assert fuzz.run(project.root, project.cfg, use_cache=True)[0]["rule"] == "CON001"
    assert "domain.m" not in cache.load(project.root)
    assert fuzz.run(project.root, project.cfg, use_cache=True)[0]["rule"] == "CON001"  # still reported on rerun


def test_history_records_runs_and_stats_summarise(project: Project) -> None:
    project.write("domain/m.py", "import os\n\n" + GOOD)
    pipeline.check(project.root)
    project.write("domain/m.py", GOOD)
    pipeline.check(project.root)
    runs = history.load(project.root)
    assert [r["ok"] for r in runs] == [False, True]
    stats = history.stats(project.root)
    assert stats["runs"] == 2 and stats["passed"] == 1 and stats["attempts_before_ok"]["average"] == 1.0
    assert stats["top_rules"]


def test_history_can_be_disabled(project: Project) -> None:
    project.write(
        "aif.toml", project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]\nhistory = false\n", 1)
    )
    project.write("domain/m.py", GOOD)
    pipeline.check(project.root)
    assert history.load(project.root) == []


def test_stats_without_history(project: Project) -> None:
    assert history.stats(project.root)["runs"] == 0


def test_status_before_any_check(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["status", "--root", str(project.root)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "none"


def test_background_check_writes_result_and_status_reports_it(
    project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    project.write("domain/m.py", GOOD)
    assert cli.main(["check", "--background", "--root", str(project.root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "running"
    state: dict[str, Any] = {}
    for _ in range(100):
        state = history.read_last(project.root)
        if state.get("status") == "done":
            break
        time.sleep(0.3)
    assert state["status"] == "done" and state["ok"] is True
    assert cli.main(["status", "--root", str(project.root)]) == 0


def test_sequential_mode_matches_parallel(project: Project) -> None:
    project.write(
        "aif.toml", project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]\nparallel = false\n", 1)
    )
    project.write("domain/m.py", GOOD.replace("x + 1", "x - 1"))
    out = pipeline.check(project.root)
    assert out["errors"][0]["rule"] == "CON001"


def test_stats_average_uses_total_not_the_sum_of_stages(project: Project) -> None:
    project.write("domain/m.py", GOOD)
    pipeline.check(project.root)
    stats = history.stats(project.root)
    last = history.load(project.root)[-1]["timings"]
    assert stats["average_seconds"] == round(last["total"], 2)
    assert "total" not in stats["average_seconds_per_stage"]

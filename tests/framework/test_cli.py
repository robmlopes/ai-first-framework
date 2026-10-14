from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import aif
from aif import cli
from tests.framework.conftest import Project

GOOD = """from aif import contract


@contract(requires=lambda x: x > 0, ensures=lambda r, x: r > x, effects=[])
def inc(x: int) -> int:
    return x + 1
"""


def run_check(project: Project, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, dict[str, Any]]:
    code = cli.main(["check", "--json", "--root", str(project.root), *extra])
    return code, json.loads(capsys.readouterr().out)


def test_check_ok(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", GOOD)
    code, out = run_check(project, capsys)
    assert code == 0 and out == {"ok": True, "errors": []}
    assert (project.root / ".aif/index.json").is_file()


def test_check_lint_error_stops_before_tests(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", "import os\n\nos.getcwd()\n")
    project.write("tests/test_x.py", "def test_x() -> None:\n    assert False\n")
    code, out = run_check(project, capsys)
    assert code == 1
    assert {e["stage"] for e in out["errors"]} <= {"lint", "effects"}
    assert "lint" in {e["stage"] for e in out["errors"]}


def test_check_reports_contract_counterexample(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    """A broken implementation is caught by fuzzing even when no test exercises the bad case."""
    project.write("domain/m.py", GOOD.replace("x + 1", "x - 1"))
    project.write("tests/test_m.py", "from domain.m import inc\n\n\ndef test_inc() -> None:\n    inc(3)\n")
    code, out = run_check(project, capsys)
    assert code == 1
    err = out["errors"][0]
    assert err["stage"] == "fuzz" and err["rule"] == "CON001"
    assert err["counterexample"]["inputs"]["x"].lstrip("-").isdigit()


def test_check_reports_test_stage_contract_violation(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    """With fuzzing off, the violation is still reported by the test stage with its counterexample."""
    text = (project.root / "aif.toml").read_text().replace("[aif]\n", "[aif]\nfuzz = false\n", 1)
    project.write("aif.toml", text)
    project.write("domain/m.py", GOOD.replace("x + 1", "x - 1"))
    project.write("tests/test_m.py", "from domain.m import inc\n\n\ndef test_inc() -> None:\n    inc(3)\n")
    framework = Path(aif.__file__).resolve().parent.parent
    project.write("pyproject.toml", f'[tool.pytest.ini_options]\npythonpath = [".", "{framework.as_posix()}"]\n')
    code, out = run_check(project, capsys)
    assert code == 1
    err = out["errors"][0]
    assert err["stage"] == "tests" and err["cause"] == "contract violated"
    assert err["kind"] == "postcondition" and err["function"] == "domain.m.inc"
    assert err["counterexample"]["inputs"] == {"x": 3}


def test_check_style_error_first(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", GOOD + "\ny   =  1\n")
    _, out = run_check(project, capsys)
    assert {e["stage"] for e in out["errors"]} == {"style"}


def test_check_intents_stage(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", GOOD)
    project.write(".aif/intents/x.md", "# T\n")
    _, out = run_check(project, capsys)
    assert {e["stage"] for e in out["errors"]} == {"intents"}


def test_index_command(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", GOOD)
    assert cli.main(["index", "--root", str(project.root)]) == 0
    assert "domain.m" in json.loads((project.root / ".aif/index.json").read_text())


def test_fix_command(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("adapters/a.py", "x   =  1\n")
    assert cli.main(["fix", "--root", str(project.root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_patch_command_from_file(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", GOOD)
    new = project.write(
        "new.py", "@contract(requires=lambda x: x > 0, effects=[])\ndef inc(x: int) -> int:\n    return x + 2\n"
    )
    code = cli.main(["patch", "domain/m.py", "inc", "--from", str(new), "--root", str(project.root)])
    assert code == 0 and "x + 2" in (project.root / "domain/m.py").read_text()


def test_patch_requires_args(project: Project) -> None:
    with pytest.raises(SystemExit):
        cli.main(["patch", "--root", str(project.root)])


def test_intent_commands(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    root = str(project.root)
    assert cli.main(["intent", "new", "feat-a", "Feat", "A", "--root", root]) == 0
    capsys.readouterr()
    assert cli.main(["intent", "list", "--root", root]) == 0
    assert json.loads(capsys.readouterr().out)["intents"][0]["id"] == "feat-a"
    msg = project.write("msg.txt", "x\n\nIntent: feat-a\n")
    assert cli.main(["intent", "commit-msg", str(msg), "--root", root]) == 0
    bad = project.write("bad.txt", "x\n")
    assert cli.main(["intent", "commit-msg", str(bad), "--root", root]) == 1
    assert cli.main(["intent", "bogus", "--root", root]) == 2


def test_human_readable_output(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write("domain/m.py", "import os\n\nos.getcwd()\n")
    assert cli.main(["check", "--root", str(project.root)]) == 1
    assert "error(s)" in capsys.readouterr().out

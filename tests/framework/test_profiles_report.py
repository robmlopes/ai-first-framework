from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from aif import cli, fuzz, scaffold
from tests.framework.conftest import Project

HEAD = "from aif import contract\n\n\n"


def test_cli_profile_creates_entry_layer(tmp_path: Path) -> None:
    out = scaffold.init(tmp_path, git=False, profile="cli")
    assert out["ok"] and out["profile"] == "cli"
    cfg = tomllib.loads((tmp_path / "aif.toml").read_text())["aif"]
    assert cfg["entry_dirs"] == ["cli"] and cfg["limits"]["cli"]["max_function_lines"] == 60
    assert (tmp_path / "cli/main.py").is_file() and (tmp_path / "tests/test_cli.py").is_file()
    assert "- cli/main.py" in (tmp_path / ".aif/intents/bootstrap.md").read_text()


def test_cli_profile_project_passes_check(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False, profile="cli")
    result = cli.check(tmp_path)
    assert result["ok"], result["errors"]


def test_web_profile_declares_framework_and_dev_dependencies(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False, profile="web-api")
    cfg = tomllib.loads((tmp_path / "aif.toml").read_text())["aif"]
    assert cfg["third_party"] == ["fastapi"] and cfg["composition_roots"] == ["web.main"]
    project = tomllib.loads((tmp_path / "pyproject.toml").read_text())["project"]
    assert {"fastapi", "httpx"} <= set(project["optional-dependencies"]["dev"])
    assert (
        "web*"
        in tomllib.loads((tmp_path / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"]["find"]["include"]
    )


def test_unknown_profile_is_rejected_without_writing(tmp_path: Path) -> None:
    out = scaffold.init(tmp_path / "x", git=False, profile="nope")
    assert out["ok"] is False and "web-api" in out["suggestion"] and not (tmp_path / "x").exists()


def test_no_profile_keeps_the_base_layout(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False)
    assert not (tmp_path / "web").exists() and "entry_dirs = [" not in (tmp_path / "aif.toml").read_text().replace(
        "# entry_dirs", ""
    )


def test_profile_flag_reaches_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["init", str(tmp_path / "p"), "--no-git", "--profile", "cli"]) == 0
    assert json.loads(capsys.readouterr().out)["profile"] == "cli"


def fuzz_report(project: Project, src: str) -> dict[str, object]:
    project.write("domain/m.py", HEAD + src)
    return fuzz.report(project.root, project.cfg)


def test_report_lists_tested_and_skipped_with_reasons(project: Project) -> None:
    src = (
        "@contract(requires=lambda x: 0 <= x <= 10, ensures=lambda r, x: r >= x)\n"
        "def tested(x: int) -> int:\n    return x + 1\n\n\n"
        "@contract()\n"
        "def no_ensures(x: int) -> int:\n    return x\n\n\n"
        '@contract(effects=["db.write"])\n'
        "def with_effect(x: int) -> int:\n    return x\n\n\n"
        "def plain(x: int) -> int:\n    return x\n\n\n"
        "def _private(x: int) -> int:\n    return x\n"
    )
    report = fuzz_report(project, src)
    assert report["ok"] is True
    tested = {t["function"]: t for t in report["tested"]}  # type: ignore[attr-defined]
    assert set(tested) == {"tested"} and tested["tested"]["status"] == "passed"
    assert tested["tested"]["examples"] > 0 and tested["tested"]["bounds_from_requires"] == {"x": [0, 10]}
    skipped = {s["function"]: s["reason"] for s in report["skipped"]}  # type: ignore[attr-defined]
    assert set(skipped) == {"no_ensures", "with_effect", "plain"}
    assert (
        "no `ensures`" in skipped["no_ensures"]
        and "effects" in skipped["with_effect"]
        and skipped["plain"] == "no @contract"
    )
    assert report["summary"]["skipped"] == 3 and report["summary"]["functions_fuzzed"] == 1  # type: ignore[index]


def test_report_marks_failures_and_ungeneratable_inputs(project: Project) -> None:
    src = (
        "@contract(ensures=lambda r, x: r > x)\ndef bad(x: int) -> int:\n    return x - 1\n\n\n"
        "@contract(ensures=lambda r, x: True)\ndef opaque(x) -> int:\n    return 1\n"
    )
    report = fuzz_report(project, src)
    status = {t["function"]: t["status"] for t in report["tested"]}  # type: ignore[attr-defined]
    assert report["ok"] is False and status == {"bad": "failed", "opaque": "not-generated"}
    assert {e["rule"] for e in report["errors"]} == {"CON001", "CON003"}  # type: ignore[attr-defined]


def test_report_command(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write(
        "domain/m.py", HEAD + "@contract(ensures=lambda r, x: r > x)\ndef f(x: int) -> int:\n    return x + 1\n"
    )
    assert cli.main(["fuzz", "--report", "--root", str(project.root)]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["functions_fuzzed"] == 1


def test_report_with_fuzz_disabled(project: Project) -> None:
    project.write(
        "aif.toml", project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]\nfuzz = false\n", 1)
    )
    assert fuzz.report(project.root, project.cfg)["summary"] == {"config": {"fuzz": False}}

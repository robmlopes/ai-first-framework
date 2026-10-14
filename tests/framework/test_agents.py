from __future__ import annotations

import json

import pytest

from aif import agents, cli
from tests.framework.conftest import Project


def test_write_generates_all_targets(project: Project) -> None:
    project.write(".aif/protocol.md", "1. Be careful.\n")
    assert sorted(agents.write(project.root)) == sorted(agents.TARGETS)
    for name in agents.TARGETS:
        text = (project.root / name).read_text()
        assert "1. Be careful." in text and "Do not edit by hand" in text
    assert (project.root / ".cursor/rules/aif.mdc").read_text().startswith("---\n")
    assert agents.stale(project.root) == []


def test_stale_detects_missing_and_edited(project: Project) -> None:
    project.write(".aif/protocol.md", "1. A.\n")
    assert sorted(agents.stale(project.root)) == sorted(agents.TARGETS)
    agents.write(project.root)
    (project.root / "AGENTS.md").write_text("tampered")
    project.write(".aif/protocol.md", "1. B.\n")
    assert sorted(agents.stale(project.root)) == sorted(agents.TARGETS)


def test_check_reports_agt001_and_command_fixes_it(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write(".aif/protocol.md", "1. A.\n")
    assert cli.check(project.root)["errors"][0]["rule"] == "AGT001"
    assert cli.main(["agents", "--root", str(project.root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert cli.check(project.root)["ok"]


def test_no_protocol_file_means_no_agent_check(project: Project) -> None:
    assert cli.check(project.root)["ok"]

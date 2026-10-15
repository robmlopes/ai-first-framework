from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from aif import cli, env, scaffold, upgrade
from tests.framework.conftest import Project


def fake_venv(root: Path, script: str) -> Path:
    """A `.venv` whose interpreter is a shell script, so a re-exec is observable."""
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(script)
    python.chmod(python.stat().st_mode | stat.S_IEXEC)
    return python


def test_no_venv_means_run_here(project: Project) -> None:
    assert env.project_python(project.root) is None
    assert env.reexec(project.root, "check", ["check"]) is None


def test_venv_is_found(project: Project) -> None:
    python = fake_venv(project.root, "#!/bin/sh\n")
    assert env.project_python(project.root) == python


def test_current_interpreter_venv_is_not_a_foreign_one(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_venv(project.root, "#!/bin/sh\n")
    monkeypatch.setattr(sys, "prefix", str(project.root / ".venv"))
    assert env.foreign_interpreter(project.root) is None
    assert env.reexec(project.root, "check", ["check"]) is None


def test_reexec_runs_the_project_interpreter_and_returns_its_exit_code(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(env.GUARD, raising=False)
    fake_venv(project.root, '#!/bin/sh\n[ "$AIF_IN_PROJECT_ENV" = 1 ] && exit 7\nexit 9\n')
    monkeypatch.setattr(env, "_framework_env", lambda python: {"PATH": "/usr/bin:/bin"})
    assert env.reexec(project.root, "check", ["check", "--json"]) == 7


def test_commands_that_do_not_run_project_code_stay_in_process(project: Project) -> None:
    fake_venv(project.root, "#!/bin/sh\nexit 7\n")
    for command in ("status", "stats", "docs", "init", "agents", "intent", "upgrade"):
        assert env.reexec(project.root, command, [command]) is None


def test_guard_prevents_a_second_reexec(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_venv(project.root, "#!/bin/sh\nexit 7\n")
    monkeypatch.setenv(env.GUARD, "1")
    assert env.reexec(project.root, "check", ["check"]) is None


def test_not_installed_hint_names_the_project_environment(project: Project) -> None:
    assert env.hint(project.root) == ""
    python = fake_venv(project.root, "#!/bin/sh\n")
    assert str(python) in env.hint(project.root) and "not the project's environment" in env.hint(project.root)


def test_cli_delegates_to_the_project_environment(project: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env, "reexec", lambda root, command, argv: 5 if command == "check" else None)
    assert cli.main(["check", "--root", str(project.root)]) == 5


# ---- upgrade ------------------------------------------------------------------------------------------------
def old_project(tmp_path: Path) -> Path:
    scaffold.init(tmp_path, git=True)
    (tmp_path / "aif.toml").write_text(
        '[aif]\nsource_dirs = ["domain"]\nforbidden_imports = ["os", "datetime"]\nmax_file_lines = 150\n'
    )
    (tmp_path / ".aif" / "protocol.md").write_text("old protocol\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    (tmp_path / ".git" / "hooks" / "pre-commit").write_text("old hook\n")
    return tmp_path


def test_upgrade_without_apply_changes_nothing(tmp_path: Path) -> None:
    root = old_project(tmp_path)
    before = {p: p.read_text() for p in (root / "aif.toml", root / ".gitignore", root / ".aif" / "protocol.md")}
    out = upgrade.run(root)
    assert out["ok"] and not out["applied"] and not out["up_to_date"]
    assert out["changes"]["protocol"] is True and ".aif/history.jsonl" in out["changes"]["gitignore"]
    assert "pre-commit" in out["changes"]["hooks"] and "history" in out["changes"]["config_added"]
    assert {p: p.read_text() for p in before} == before


def test_upgrade_apply_updates_framework_files_and_keeps_user_values(tmp_path: Path) -> None:
    root = old_project(tmp_path)
    out = upgrade.run(root, apply=True)
    assert out["applied"] and out["next"] == ["aif check --json"]
    assert (root / ".aif" / "protocol.md").read_text() == scaffold.template("protocol.md")
    assert (root / ".git" / "hooks" / "pre-commit").read_text() == scaffold.template("pre-commit")
    gitignore = (root / ".gitignore").read_text()
    assert gitignore.startswith("__pycache__/\n") and ".aif/history.jsonl" in gitignore
    config = (root / "aif.toml").read_text()
    assert "max_file_lines = 150" in config and 'forbidden_imports = ["os", "datetime"]' in config
    assert "history = true" in config and "# added by `aif upgrade`" in config
    assert "AGENTS.md" not in str(out["changes"]["agent_files"]) or (root / "AGENTS.md").is_file()


def test_upgrade_reports_stale_values_instead_of_editing_them(tmp_path: Path) -> None:
    root = old_project(tmp_path)
    (note,) = upgrade.run(root)["manual"]
    assert "datetime" in note and "forbidden_clock" in note
    upgrade.run(root, apply=True)
    assert '"datetime"' in (root / "aif.toml").read_text()


def test_upgrade_is_idempotent(tmp_path: Path) -> None:
    root = old_project(tmp_path)
    upgrade.run(root, apply=True)
    again = upgrade.run(root, apply=True)
    assert again["up_to_date"] and again["next"] == []


def test_upgrade_requires_an_aif_project(tmp_path: Path) -> None:
    out = upgrade.run(tmp_path)
    assert out["ok"] is False and "aif init" in out["suggestion"]


def test_upgrade_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = old_project(tmp_path)
    assert cli.main(["upgrade", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["up_to_date"] is False
    assert cli.main(["upgrade", "--apply", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is True


def test_upgrade_keeps_the_projects_own_protocol_sections(tmp_path: Path) -> None:
    root = old_project(tmp_path)
    own = "## Team rules\n\n11. Never swallow errors.\n12. Use the harness.\n"
    (root / ".aif" / "protocol.md").write_text("1. old rule\n\n" + own)
    assert upgrade.run(root)["changes"]["protocol"] is True
    upgrade.run(root, apply=True)
    text = (root / ".aif" / "protocol.md").read_text()
    assert text.startswith(scaffold.template("protocol.md").rstrip("\n")) and text.endswith(own)
    assert "1. old rule" not in text
    assert agents_in_sync(root) and upgrade.run(root)["up_to_date"]


def agents_in_sync(root: Path) -> bool:
    from aif import agents

    return agents.stale(root) == []

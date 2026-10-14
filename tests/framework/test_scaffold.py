from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aif import cli, scaffold
from aif.config import load


def test_init_creates_structure(tmp_path: Path) -> None:
    out = scaffold.init(tmp_path / "my_app", git=False)
    root = tmp_path / "my_app"
    assert out["ok"] and out["git_hooks_installed"] is False
    for rel in ("aif.toml", "pyproject.toml", ".aif/protocol.md", "AGENTS.md", "CLAUDE.md", ".cursor/rules/aif.mdc"):
        assert (root / rel).is_file(), rel
    for pkg in ("domain", "ports", "adapters", "tests"):
        assert (root / pkg / "__init__.py").read_text() == ""
    assert 'name = "my-app"' in (root / "pyproject.toml").read_text()
    assert (root / "scripts/pre-commit").stat().st_mode & 0o111


def test_init_config_loads_and_matches_defaults(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False)
    cfg = load(tmp_path)
    assert cfg.pure_dirs == ["domain"] and cfg.fuzz and cfg.fuzz_setup == "tests.strategies"


def test_new_project_passes_check(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False)
    result = cli.check(tmp_path)
    assert result["ok"] and result["errors"] == []


def test_init_refuses_existing_project(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False)
    out = scaffold.init(tmp_path, git=False)
    assert out["ok"] is False and "aif.toml" in out["cause"]


def test_init_does_not_overwrite_existing_files(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("custom\n")
    scaffold.init(tmp_path, git=False)
    assert (tmp_path / ".gitignore").read_text() == "custom\n"


def test_init_with_git_installs_hooks(tmp_path: Path) -> None:
    out = scaffold.init(tmp_path, git=True)
    assert out["git_hooks_installed"] is True
    for hook in ("pre-commit", "commit-msg"):
        assert (tmp_path / ".git/hooks" / hook).stat().st_mode & 0o111
    assert subprocess.run(["git", "rev-parse"], cwd=tmp_path, capture_output=True).returncode == 0


def test_init_inside_existing_repo_does_not_reinit(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    head = (tmp_path / ".git/HEAD").read_text()
    scaffold.init(tmp_path, git=True)
    assert (tmp_path / ".git/HEAD").read_text() == head


def test_templates_match_framework_hooks() -> None:
    root = Path(scaffold.__file__).resolve().parent.parent
    for hook in scaffold.HOOKS:
        assert scaffold.template(hook) == (root / "scripts" / hook).read_text(), hook


def test_cli_init_and_fuzz(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "proj"
    assert cli.main(["init", str(target), "--no-git"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    (target / "domain").mkdir(exist_ok=True)
    (target / "domain/m.py").write_text(
        "from aif import contract\n\n\n@contract(ensures=lambda r, x: r > x)\ndef f(x: int) -> int:\n    return x - 1\n"
    )
    assert cli.main(["fuzz", "--root", str(target)]) == 1
    errors = json.loads(capsys.readouterr().out)["errors"]
    assert errors[0]["rule"] == "CON001"


def test_cli_init_existing_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scaffold.init(tmp_path, git=False)
    assert cli.main(["init", str(tmp_path), "--no-git"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_new_project_has_clock_port_and_rejects_clock_reads(tmp_path: Path) -> None:
    scaffold.init(tmp_path, git=False)
    assert "class Clock" in (tmp_path / "ports/clock.py").read_text()
    (tmp_path / "domain/m.py").write_text(
        "import time\n\nfrom aif import contract\n\n\n"
        "@contract(effects=[])\ndef t() -> float:\n    return time.time()\n"
    )
    errors = cli.check(tmp_path)["errors"]
    assert errors and errors[0]["rule"] == "AIF010"

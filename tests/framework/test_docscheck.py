from __future__ import annotations

import json
from pathlib import Path

import pytest

from aif import cli, docscheck, pipeline
from tests.framework.conftest import Project

COMMANDS = ["check", "docs"]


def write_docs(
    project: Project, rules: str = "", config: str = "", cli_doc: str = "", extra: dict[str, str] | None = None
) -> None:
    project.write("docs/lint-rules.md", rules)
    project.write("docs/configuration.md", config)
    project.write("docs/cli.md", cli_doc)
    for name, text in (extra or {}).items():
        project.write(f"docs/{name}", text)


def fake_package(tmp_path: Path, ids: list[str]) -> Path:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "m.py").write_text("\n".join(f'RULE = "{i}"' for i in ids) + '\n"""AIF999 only in a docstring"""\n')
    return package


def test_no_docs_directory_means_no_checks(project: Project) -> None:
    assert docscheck.run(project.root, COMMANDS) == []


def test_undocumented_rule_is_doc001(project: Project, tmp_path: Path) -> None:
    write_docs(project, rules="AIF001 documented")
    errors = docscheck.check_rules(project.root, fake_package(tmp_path, ["AIF001", "AIF002"]))
    assert [(e["rule"], "AIF002" in e["cause"]) for e in errors] == [("DOC001", True)]


def test_documented_but_never_emitted_rule_is_doc001(project: Project, tmp_path: Path) -> None:
    write_docs(project, rules="AIF001 and AIF003")
    errors = docscheck.check_rules(project.root, fake_package(tmp_path, ["AIF001"]))
    assert len(errors) == 1 and "AIF003" in errors[0]["cause"] and "no code emits" in errors[0]["cause"]


def test_rule_documented_in_any_doc_file_counts(project: Project, tmp_path: Path) -> None:
    write_docs(project, rules="AIF001", extra={"contracts.md": "see CON001"})
    assert docscheck.check_rules(project.root, fake_package(tmp_path, ["AIF001", "CON001"])) == []


def test_docstring_mentions_are_not_emitted_rules(tmp_path: Path) -> None:
    assert docscheck.emitted_rules(fake_package(tmp_path, ["AIF001"])) == {"AIF001"}


def test_undocumented_config_option_is_doc002(project: Project) -> None:
    write_docs(project, config="| `max_file_lines` | 200 |")
    errors = docscheck.check_config(project.root)
    assert errors and all(e["rule"] == "DOC002" for e in errors)
    assert any("max_function_lines" in e["cause"] for e in errors)
    assert not any("max_file_lines" in e["cause"] for e in errors)


def test_undocumented_command_is_doc003(project: Project) -> None:
    write_docs(project, cli_doc="| `check` | runs |")
    errors = docscheck.check_cli(project.root, COMMANDS)
    assert [e["rule"] for e in errors] == ["DOC003"] and "docs" in errors[0]["cause"]


def test_broken_relative_link_is_doc004(project: Project) -> None:
    write_docs(project, extra={"a.md": "[x](missing.md) and [ok](b.md)", "b.md": "# B"})
    errors = docscheck.check_links(project.root)
    assert [e["rule"] for e in errors] == ["DOC004"] and "missing.md" in errors[0]["cause"]


def test_link_anchors_are_verified(project: Project) -> None:
    write_docs(
        project,
        extra={"a.md": "[ok](b.md#hello-world) [bad](b.md#nope) [self](#top)\n# Top", "b.md": "## Hello, World!"},
    )
    errors = docscheck.check_links(project.root)
    assert len(errors) == 1 and "#nope" in errors[0]["cause"]


def test_external_links_and_code_blocks_are_ignored(project: Project) -> None:
    text = "[web](https://example.com) [mail](mailto:a@b.c)\n```\n[fake](nowhere.md)\n```\n"
    write_docs(project, extra={"a.md": text})
    assert docscheck.check_links(project.root) == []


def test_docs_stage_is_off_by_default_and_opt_in(project: Project) -> None:
    write_docs(project, extra={"a.md": "[x](missing.md)"})
    assert pipeline.check(project.root)["ok"]
    project.write(
        "aif.toml", project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]\ndocs_check = true\n", 1)
    )
    out = pipeline.check(project.root)
    assert not out["ok"] and out["errors"][0]["stage"] == "docs"


def test_docs_command(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    write_docs(project, extra={"a.md": "[x](missing.md)"})
    assert cli.main(["docs", "--root", str(project.root)]) == 1
    assert "DOC004" in {e["rule"] for e in json.loads(capsys.readouterr().out)["errors"]}


def test_this_repository_documentation_agrees_with_the_code() -> None:
    root = Path(__file__).resolve().parents[2]
    assert docscheck.run(root, pipeline.COMMANDS) == []

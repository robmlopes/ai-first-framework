from __future__ import annotations

from typing import Any

from aif import intents
from tests.framework.conftest import Project

VALID = """# Title

## Why
Because.

## Scope
- domain/m.py

## Acceptance
- It works.
"""


def run(project: Project) -> list[dict[str, Any]]:
    return intents.run(project.root, project.cfg)


def test_valid_intent_ok(project: Project) -> None:
    project.write("domain/m.py", "")
    project.write(".aif/intents/my-feature.md", VALID)
    assert run(project) == []


def test_no_intents_dir_ok(project: Project) -> None:
    assert run(project) == []


def test_int001_bad_id(project: Project) -> None:
    project.write("domain/m.py", "")
    project.write(".aif/intents/Bad_Name.md", VALID)
    assert project.rules(run(project)) == ["INT001"]


def test_int002_empty_sections_and_title(project: Project) -> None:
    project.write(".aif/intents/x.md", "## Why\n\n## Scope\n\n")
    errors = run(project)
    assert set(project.rules(errors)) == {"INT002"}
    assert len(errors) == 4  # title, Why, Scope, Acceptance


def test_int003_scope_path_missing(project: Project) -> None:
    project.write(".aif/intents/x.md", VALID)
    assert project.rules(run(project)) == ["INT003"]


def test_create_and_duplicate(project: Project) -> None:
    out = intents.create(project.root, project.cfg, "new-one", "New one")
    assert out["ok"] and (project.root / ".aif/intents/new-one.md").is_file()
    assert not intents.create(project.root, project.cfg, "new-one", "again")["ok"]
    assert not intents.create(project.root, project.cfg, "Bad Id", "x")["ok"]


def test_template_fails_validation_until_filled(project: Project) -> None:
    intents.create(project.root, project.cfg, "tpl", "Tpl")
    assert project.rules(run(project)) == ["INT003"]  # placeholder scope path


def test_listing(project: Project) -> None:
    project.write("domain/m.py", "")
    project.write(".aif/intents/x.md", VALID)
    assert intents.listing(project.root) == [{"id": "x", "title": "Title", "scope": ["domain/m.py"]}]


def test_commit_message_trailer(project: Project) -> None:
    project.write(".aif/intents/x.md", VALID)
    assert intents.check_message(project.root, "feat\n\nIntent: x\n") is None
    no_trailer = intents.check_message(project.root, "feat\n")
    unknown = intents.check_message(project.root, "feat\n\nIntent: nope\n")
    assert no_trailer is not None and no_trailer["rule"] == "INT004"
    assert unknown is not None and unknown["rule"] == "INT005"


def test_int006_changed_file_outside_scope(project: Project) -> None:
    project.write(".aif/intents/x.md", VALID)
    msg = "feat\n\nIntent: x\n"
    errs = intents.check_scope(
        project.root, msg, ["domain/m.py", "adapters/other.py", "docs/a.md", "tests/t.py", "README.md"]
    )
    assert project.rules(errs) == ["INT006"] and errs[0]["file"] == "adapters/other.py"


def test_scope_skipped_without_valid_intent(project: Project) -> None:
    assert intents.check_scope(project.root, "no trailer", ["adapters/a.py"]) == []
    assert intents.check_scope(project.root, "Intent: ghost", ["adapters/a.py"]) == []


def test_scope_ignores_empty_init_but_not_code(project: Project) -> None:
    project.write(".aif/intents/x.md", VALID)
    project.write("adapters/empty/__init__.py", "")
    project.write("adapters/full/__init__.py", "X = 1\n")
    errs = intents.check_scope(project.root, "Intent: x", ["adapters/empty/__init__.py", "adapters/full/__init__.py"])
    assert [e["file"] for e in errs] == ["adapters/full/__init__.py"]

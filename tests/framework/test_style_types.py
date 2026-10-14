from __future__ import annotations

from pathlib import Path

import pytest

import aif
from aif import style, types
from tests.framework.conftest import Project


def test_style_clean(project: Project) -> None:
    project.write("adapters/a.py", "x = 1\n")
    assert style.run(project.root, project.cfg) == []


def test_style_reports_format_and_ruff_codes(project: Project) -> None:
    project.write("adapters/a.py", "import os\nx   =  1\n")
    rules = project.rules(style.run(project.root, project.cfg))
    assert "format" in rules and "F401" in rules


def test_fix_repairs_what_it_can(project: Project) -> None:
    project.write("adapters/a.py", "import os\nx   =  1\n")
    out = style.fix(project.root, project.cfg)
    assert out["ok"], out
    assert (project.root / "adapters/a.py").read_text() == "x = 1\n"


def test_style_can_be_disabled(project: Project) -> None:
    project.write("aif.toml", (project.root / "aif.toml").read_text().replace("[aif]\n", "[aif]\nstyle = false\n"))
    project.write("adapters/a.py", "x   =  1\n")
    assert style.run(project.root, project.cfg) == []


def test_types_clean(project: Project) -> None:
    project.write("adapters/a.py", "def f(x: int) -> int:\n    return x\n")
    assert types.run(project.root, project.cfg) == []


def test_types_reports_mismatch_with_hint(project: Project) -> None:
    project.write("adapters/a.py", 'def f(x: int) -> int:\n    return "s"\n')
    errors = types.run(project.root, project.cfg)
    assert [e["rule"] for e in errors] == ["return-value"]
    assert errors[0]["line"] == 2 and errors[0]["suggestion"]


def test_types_checks_adapter_against_port(project: Project) -> None:
    project.write(
        "adapters/a.py",
        "from ports.db import DbWrite\n\n\nclass Good:\n    def save(self, value: int) -> None: ...\n\n\n"
        "class Bad:\n    def store(self, value: int) -> None: ...\n\n\n"
        "def ok(x: Good) -> DbWrite:\n    return x\n\n\ndef bad(x: Bad) -> DbWrite:\n    return x\n",
    )
    errors = types.run(project.root, project.cfg)
    assert [e["line"] for e in errors] == [17]


def test_types_cover_tests_dir_by_default(project: Project) -> None:
    project.write("tests/test_x.py", "def test_x(a) -> None:\n    pass\n")
    errors = types.run(project.root, project.cfg)
    assert [e["file"] for e in errors] == ["tests/test_x.py"]


def test_typecheck_tests_can_be_disabled(project: Project) -> None:
    project.write(
        "aif.toml", (project.root / "aif.toml").read_text().replace("[aif]\n", "[aif]\ntypecheck_tests = false\n")
    )
    project.write("tests/test_x.py", "def test_x(a) -> None:\n    pass\n")
    assert types.run(project.root, project.cfg) == []


def test_framework_path_added_only_for_source_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aif import types as aif_types

    fake = tmp_path / "site-packages" / "aif"
    fake.mkdir(parents=True)
    monkeypatch.setattr(aif, "__file__", str(fake / "__init__.py"))
    assert aif_types._framework_path() == []  # installed: mypy finds it, and rejects site-packages in MYPYPATH
    checkout = tmp_path / "src" / "aif"
    checkout.mkdir(parents=True)
    monkeypatch.setattr(aif, "__file__", str(checkout / "__init__.py"))
    assert aif_types._framework_path() == [str(checkout.parent)]

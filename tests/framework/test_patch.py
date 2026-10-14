from __future__ import annotations

from typing import Any

from aif import patch
from tests.framework.conftest import Project

SRC = """from aif import contract


@contract(requires=lambda x: x > 0, effects=[])
def f(x: int) -> int:
    return x


class Box:
    def get(self) -> int:
        return 1

    def put(self) -> None:
        pass


@contract(effects=[])
def g() -> int:
    return 2
"""


def apply(project: Project, symbol: str, new: str, **kw: bool) -> dict[str, Any]:
    return patch.apply(project.root, project.cfg, "domain/m.py", symbol, new, **kw)


def test_replaces_only_target_function(project: Project) -> None:
    project.write("domain/m.py", SRC)
    new = "@contract(requires=lambda x: x > 0, effects=[])\ndef f(x: int) -> int:\n    return x + 1\n"
    out = apply(project, "f", new)
    assert out["ok"], out
    text = (project.root / "domain/m.py").read_text()
    assert "return x + 1" in text and "def g()" in text and "class Box" in text


def test_patch_method_reindents(project: Project) -> None:
    project.write("domain/m.py", SRC)
    out = apply(project, "Box.get", "def get(self) -> int:\n    return 99\n")
    assert out["ok"], out
    text = (project.root / "domain/m.py").read_text()
    assert "    def get(self) -> int:\n        return 99\n" in text
    assert "def put(self)" in text


def test_dry_run_does_not_write(project: Project) -> None:
    project.write("domain/m.py", SRC)
    out = apply(project, "Box.get", "def get(self) -> int:\n    return 99\n", dry_run=True)
    assert out["ok"] and out["dry_run"] and "return 99" in out["diff"]
    assert "return 99" not in (project.root / "domain/m.py").read_text()


def test_lint_failure_rolls_back(project: Project) -> None:
    project.write("domain/m.py", SRC)
    out = apply(project, "Box.get", "def get(self):\n    return 99\n")
    assert not out["ok"] and out["rolled_back"]
    assert project.rules(out["errors"]) == ["AIF003"]
    assert (project.root / "domain/m.py").read_text() == SRC


def test_keep_flag_preserves_change(project: Project) -> None:
    project.write("domain/m.py", SRC)
    out = apply(project, "Box.get", "def get(self):\n    return 99\n", keep=True)
    assert out["ok"] and out["errors"]
    assert "return 99" in (project.root / "domain/m.py").read_text()


def test_rejections(project: Project) -> None:
    project.write("domain/m.py", SRC)
    assert "expected 'f'" in apply(project, "f", "def other() -> None: ...")["cause"]
    assert "not found" in apply(project, "nope", "def nope() -> None: ...")["cause"]
    assert "syntax error" in apply(project, "f", "def f(")["cause"]
    assert "exactly one" in apply(project, "f", "x = 1")["cause"]
    assert "not a class" in apply(project, "Box.get", "class get: ...")["cause"]
    assert "not found" in apply(project, "Box.nope", "def nope(self) -> None: ...")["cause"]


def test_rejects_paths_outside_source_dirs(project: Project) -> None:
    project.write("tests_dir/x.py", "x = 1\n")
    for bad in ("../outside.py", "tests_dir/x.py", "domain/m.txt"):
        out = patch.apply(project.root, project.cfg, bad, "f", "def f() -> None: ...")
        assert not out["ok"] and "not a Python file" in out["cause"]

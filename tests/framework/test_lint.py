from __future__ import annotations

from aif import lint

GOOD = """from aif import contract


@contract(requires=lambda x: x > 0, effects=[])
def f(x: int) -> int:
    return x
"""


def run(project):
    return lint.run(project.root, project.cfg)


def test_clean_project_has_no_errors(project):
    project.write("domain/m.py", GOOD)
    assert run(project) == []


def test_aif001_forbidden_import_in_domain(project):
    project.write("domain/m.py", "import os\n")
    assert project.rules(run(project)) == ["AIF001"]


def test_aif001_allowed_in_adapters(project):
    project.write("adapters/a.py", "import sqlite3\n")
    assert run(project) == []


def test_aif002_public_function_needs_contract(project):
    project.write("domain/m.py", "def f(x: int) -> int:\n    return x\n")
    assert project.rules(run(project)) == ["AIF002"]


def test_aif002_private_function_exempt(project):
    project.write("domain/m.py", "def _f(x: int) -> int:\n    return x\n")
    assert run(project) == []


def test_aif003_missing_hints(project):
    project.write("adapters/a.py", "def f(x):\n    return x\n")
    assert project.rules(run(project)) == ["AIF003"]


def test_aif004_generic_except(project):
    src = "def f() -> None:\n    try:\n        pass\n    except Exception:\n        pass\n"
    project.write("adapters/a.py", src)
    assert project.rules(run(project)) == ["AIF004"]


def test_aif004_bare_except(project):
    src = "def f() -> None:\n    try:\n        pass\n    except:\n        pass\n"
    project.write("adapters/a.py", src)
    assert project.rules(run(project)) == ["AIF004"]


def test_aif004_typed_except_ok(project):
    src = "def f() -> None:\n    try:\n        pass\n    except ValueError:\n        pass\n"
    project.write("adapters/a.py", src)
    assert run(project) == []


def test_aif005_function_too_long(project):
    body = "\n".join(f"    x{i} = {i}" for i in range(45))
    project.write("adapters/a.py", f"def f() -> None:\n{body}\n")
    assert project.rules(run(project)) == ["AIF005"]


def test_aif005_file_too_long(project):
    project.write("adapters/a.py", "x = 1\n" * 201)
    assert project.rules(run(project)) == ["AIF005"]


def test_aif006_unknown_symbol_lists_available(project):
    project.write("domain/m.py", GOOD)
    project.write("adapters/a.py", "from domain.m import g\n")
    errors = run(project)
    assert project.rules(errors) == ["AIF006"]
    assert "'f'" in errors[0]["suggestion"]


def test_aif006_unknown_module(project):
    project.write("adapters/a.py", "from domain.nope import g\n")
    assert project.rules(run(project)) == ["AIF006"]


def test_aif006_known_symbol_ok(project):
    project.write("domain/m.py", GOOD)
    project.write("adapters/a.py", "from domain.m import f\n")
    assert run(project) == []


def test_aif007_global(project):
    project.write("adapters/a.py", "X = 1\n\n\ndef f() -> None:\n    global X\n    X = 2\n")
    assert project.rules(run(project)) == ["AIF007"]


def test_aif012_unknown_class_member(project):
    project.write("adapters/a.py", "class A:\n    def run(self) -> None: ...\n\n\nx = A.missing\n")
    assert project.rules(run(project)) == ["AIF012"]


def test_aif012_known_member_ok(project):
    project.write(
        "adapters/a.py", "class A:\n    n: int = 1\n\n    def run(self) -> None: ...\n\n\nx = A.run\ny = A.n\n"
    )
    assert run(project) == []


def test_aif012_across_modules(project):
    project.write("adapters/a.py", "class A:\n    def run(self) -> None: ...\n")
    project.write("adapters/b.py", "from adapters.a import A\n\nx = A.stop\n")
    assert project.rules(run(project)) == ["AIF012"]


def test_aif006_relative_import_unknown_symbol(project):
    project.write("domain/m.py", GOOD)
    project.write("domain/n.py", "from .m import g\n")
    errors = run(project)
    assert project.rules(errors) == ["AIF006"] and "domain.m.g" in errors[0]["cause"]


def test_aif006_relative_import_known_symbol_ok(project):
    project.write("domain/m.py", GOOD)
    project.write("domain/n.py", "from .m import f\nfrom . import m\n")
    assert run(project) == []


def test_aif006_relative_import_unknown_module(project):
    project.write("domain/n.py", "from .nope import f\n")
    assert project.rules(run(project)) == ["AIF006"]


def test_aif006_relative_from_package_init(project):
    project.write("adapters/sub/__init__.py", "from .impl import Thing\n")
    project.write("adapters/sub/impl.py", "class Thing: ...\n")
    assert run(project) == []
    project.write("adapters/sub/__init__.py", "from .impl import Other\n")
    assert project.rules(run(project)) == ["AIF006"]


def test_aif006_relative_beyond_root(project):
    project.write("domain/n.py", "from ... import x\n")
    assert project.rules(run(project)) == ["AIF006"]


def test_aif006_import_dotted_module(project):
    project.write("domain/m.py", GOOD)
    project.write("adapters/a.py", "import domain.m\nimport domain.nope\n")
    errors = run(project)
    assert project.rules(errors) == ["AIF006"] and "domain.nope" in errors[0]["cause"]


def test_aif001_relative_forbidden_not_confused(project):
    project.write("domain/os.py", "")
    project.write("domain/n.py", "from . import os\n")
    assert run(project) == []

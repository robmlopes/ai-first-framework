from __future__ import annotations

from aif import effects

HEAD = "from aif import contract\nfrom ports.db import DbWrite\n\n\n"


def run(project):
    return effects.run(project.root, project.cfg)


def test_matching_effect_and_capability_ok(project):
    project.write(
        "domain/m.py",
        HEAD + '@contract(effects=["db.write"])\ndef f(db: DbWrite) -> None:\n    db.save(1)\n',
    )
    assert run(project) == []


def test_aif009_capability_without_declared_effect(project):
    project.write("domain/m.py", HEAD + "@contract(effects=[])\ndef f(db: DbWrite) -> None:\n    db.save(1)\n")
    assert project.rules(run(project)) == ["AIF009"]


def test_aif009_declared_effect_without_capability(project):
    project.write("domain/m.py", HEAD + '@contract(effects=["db.write"])\ndef f(x: int) -> None:\n    pass\n')
    assert project.rules(run(project)) == ["AIF009"]


def test_aif008_unknown_effect(project):
    project.write("domain/m.py", HEAD + '@contract(effects=["net.read"])\ndef f(x: int) -> None:\n    pass\n')
    assert "AIF008" in project.rules(run(project))


def test_aif010_direct_call_in_domain(project):
    project.write("domain/m.py", HEAD + "@contract(effects=[])\ndef f() -> None:\n    print('x')\n")
    assert project.rules(run(project)) == ["AIF010"]


def test_aif010_not_enforced_outside_domain(project):
    project.write("adapters/a.py", "def f() -> None:\n    print('x')\n")
    assert run(project) == []


def test_aif011_domain_imports_adapter(project):
    project.write("adapters/a.py", "class A: ...\n")
    project.write("domain/m.py", "from adapters.a import A\n")
    assert project.rules(run(project)) == ["AIF011"]


def test_aif011_indirect_io_through_port(project):
    project.write("ports/leak.py", "import sqlite3\n")
    project.write("domain/m.py", "import ports.leak\n")
    errors = run(project)
    assert project.rules(errors) == ["AIF011"]
    assert "domain.m -> ports.leak -> sqlite3" in errors[0]["cause"]


def test_domain_may_import_port(project):
    project.write("domain/m.py", "from ports.db import DbWrite\n")
    assert run(project) == []


def test_aif011_domain_imports_adapter_symbol(project):
    project.write("adapters/a.py", "class A: ...\n")
    project.write("domain/m.py", "from adapters.a import A\n")
    assert project.rules(run(project)) == ["AIF011"]


def test_aif011_indirect_through_relative_import(project):
    project.write("ports/leak.py", "import sqlite3\n")
    project.write("ports/mid.py", "from . import leak\n")
    project.write("domain/m.py", "from ports import mid\n")
    errors = run(project)
    assert project.rules(errors) == ["AIF011"]
    assert "ports.mid -> ports.leak -> sqlite3" in errors[0]["cause"]


def _rules_for(project, body):
    project.write("domain/m.py", "from aif import contract\n" + body)
    return project.rules(run(project))


def test_aif010_builtins_qualified(project):
    assert _rules_for(project, "import builtins\n\n\ndef _f() -> None:\n    builtins.open('x')\n") == ["AIF010"]


def test_aif010_alias_of_builtin(project):
    assert _rules_for(project, "reader = open\n\n\ndef _f() -> None:\n    reader('x')\n") == ["AIF010"]


def test_aif010_module_function_call(project):
    assert "AIF010" in _rules_for(project, "import os\n\n\ndef _f() -> None:\n    os.getcwd()\n")


def test_aif010_from_import_alias(project):
    assert "AIF010" in _rules_for(project, "from os import getcwd as cwd\n\n\ndef _f() -> None:\n    cwd()\n")


def test_aif010_getattr_blocked(project):
    assert _rules_for(project, "def _f(x: object) -> object:\n    return getattr(x, 'a')\n") == ["AIF010"]


def test_aif010_plain_code_ok(project):
    assert _rules_for(project, "def _f(x: int) -> int:\n    return abs(x) + len([x])\n") == []


def test_capability_through_import_alias(project):
    body = (
        "from ports.db import DbWrite as Writer\n\n\n"
        '@contract(effects=["db.write"])\ndef f(db: Writer) -> None:\n    db.save(1)\n'
    )
    assert _rules_for(project, body) == []
    body = body.replace('effects=["db.write"]', "effects=[]")
    assert _rules_for(project, body) == ["AIF009"]


def test_capability_through_module_alias_and_assignment(project):
    body = (
        "import ports.db as pdb\nfrom ports.db import DbWrite\n\nCap = DbWrite\n\n\n"
        "@contract(effects=[])\ndef f(a: pdb.DbWrite, b: Cap) -> None:\n    pass\n"
    )
    errors = (
        effects.run(project.root, project.cfg)
        if project.write("domain/m.py", "from aif import contract\n" + body)
        else []
    )
    assert project.rules(errors) == ["AIF009"]


def test_capability_inside_union_generic_and_quotes(project):
    for ann in ("DbWrite | None", "list[DbWrite]", "'DbWrite'", "Optional[DbWrite]"):
        body = (
            "from typing import Optional\n\nfrom ports.db import DbWrite\n\n\n"
            f"@contract(effects=[])\ndef f(db: {ann}) -> None:\n    pass\n"
        )
        assert _rules_for(project, body) == ["AIF009"], ann

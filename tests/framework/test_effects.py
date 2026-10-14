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

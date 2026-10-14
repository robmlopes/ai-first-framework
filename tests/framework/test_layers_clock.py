from __future__ import annotations

from aif import effects
from tests.framework.conftest import Project

WEB_TOML = '\nentry_dirs = ["web"]\ncomposition_roots = ["web.main"]\n'
SQLITE = "def connect() -> int:\n    return 1\n"


def enable_web(project: Project, forbidden_imports: str | None = None) -> None:
    text = project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]" + WEB_TOML, 1)
    if forbidden_imports:
        text = text.replace('forbidden_imports = ["builtins", "os", "sqlite3", "requests"]', forbidden_imports)
    project.write("aif.toml", text)
    project.write("web/__init__.py", "")
    project.write("adapters/store.py", SQLITE)


def rules(project: Project) -> list[str]:
    return project.rules(effects.run(project.root, project.cfg))


def test_entry_dirs_join_source_dirs(project: Project) -> None:
    enable_web(project)
    assert "web" in project.cfg.source_dirs


def test_entry_layer_may_use_domain_and_ports(project: Project) -> None:
    enable_web(project)
    project.write(
        "web/routes.py", "from ports.db import DbWrite\n\n\ndef handler(db: DbWrite) -> None:\n    db.save(1)\n"
    )
    assert rules(project) == []


def test_entry_layer_importing_adapter_is_aif016(project: Project) -> None:
    enable_web(project)
    project.write("web/routes.py", "from adapters.store import connect\n\n\ndef h() -> int:\n    return connect()\n")
    errors = effects.run(project.root, project.cfg)
    assert project.rules(errors) == ["AIF016"] and "composition_roots" in errors[0]["suggestion"]


def test_composition_root_may_import_adapters(project: Project) -> None:
    enable_web(project)
    project.write("web/main.py", "from adapters.store import connect\n\n\ndef build() -> int:\n    return connect()\n")
    assert rules(project) == []


def test_entry_layer_is_not_pure(project: Project) -> None:
    enable_web(project)
    project.write("web/routes.py", "import os\n\n\ndef h() -> str:\n    return os.getcwd()\n")
    assert rules(project) == []  # I/O is allowed in entry layers


def test_type_use_of_datetime_is_not_a_clock_read(project: Project) -> None:
    src = (
        "from datetime import date, timedelta\n\n"
        "from aif import contract\n\n\n"
        "@contract(effects=[])\n"
        "def next_day(d: date) -> date:\n    return d + timedelta(days=1)\n"
    )
    project.write("domain/m.py", src)
    assert rules(project) == []


def test_clock_reads_are_banned_in_pure_code(project: Project) -> None:
    src = (
        "import datetime\nimport time\nfrom datetime import date\n\nfrom aif import contract\n\n\n"
        "@contract(effects=[])\n"
        "def a() -> object:\n    return datetime.datetime.now()\n\n\n"
        "@contract(effects=[])\n"
        "def b() -> float:\n    return time.time()\n\n\n"
        "@contract(effects=[])\n"
        "def c() -> object:\n    return date.today()\n"
    )
    project.write("domain/m.py", src)
    assert rules(project) == ["AIF010", "AIF010", "AIF010"]


def test_clock_port_is_the_recommended_fix(project: Project) -> None:
    project.write(
        "ports/clock.py",
        "from typing import Protocol\n\n\nclass Clock(Protocol):\n    def now_minute(self) -> int: ...\n",
    )
    project.write(
        "domain/m.py",
        "from aif import contract\nfrom ports.clock import Clock\n\n\n"
        "@contract(effects=[])\ndef t(c: Clock) -> int:\n    return c.now_minute()\n",
    )
    assert rules(project) == []

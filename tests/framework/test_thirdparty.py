from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aif import lint
from tests.framework.conftest import Project


def set_options(project: Project, **options: str) -> None:
    """Rewrite aif.toml with the given top-level [aif] options, keeping everything else."""
    text = (project.root / "aif.toml").read_text()
    for key, value in options.items():
        text = re.sub(rf"^{key} = .*\n", "", text, flags=re.M)
        text = text.replace("[aif]\n", f"[aif]\n{key} = {value}\n", 1)
    project.write("aif.toml", text)


def run(project: Project, src: str, third_party: str = "[]") -> list[dict[str, Any]]:
    set_options(project, third_party=third_party)
    project.write("adapters/a.py", src)
    return [e for e in lint.run(project.root, project.cfg) if e["rule"] in {"AIF014", "AIF015"}]


def rules(project: Project, src: str, third_party: str = "[]") -> list[str]:
    return [e["rule"] for e in run(project, src, third_party)]


def test_stdlib_always_allowed(project: Project) -> None:
    assert rules(project, "import json\nfrom decimal import Decimal\nfrom os.path import join\nimport sys\n") == []


def test_project_and_framework_allowed(project: Project) -> None:
    assert rules(project, "from aif import contract\nfrom ports.db import DbWrite\n") == []


def test_aif014_undeclared_package(project: Project) -> None:
    errors = run(project, "import requests\n")
    assert [e["rule"] for e in errors] == ["AIF014"]
    assert "third_party" in errors[0]["suggestion"]


def test_aif014_nonexistent_package(project: Project) -> None:
    assert rules(project, "import totally_made_up_pkg\n") == ["AIF014"]


def test_declared_package_ok(project: Project) -> None:
    assert rules(project, "import yaml\n", '["yaml"]') == []


def test_aif014_declared_but_not_installed(project: Project) -> None:
    errors = run(project, "import not_installed_xyz\n", '["not_installed_xyz"]')
    assert [e["rule"] for e in errors] == ["AIF014"] and "not installed" in errors[0]["cause"]


def test_aif015_unknown_name_in_installed_package(project: Project) -> None:
    errors = run(project, "from yaml import safe_load, safe_lod\n", '["yaml"]')
    assert [e["rule"] for e in errors] == ["AIF015"] and "yaml.safe_lod" in errors[0]["cause"]
    assert "safe_load" in errors[0]["suggestion"]


def test_aif015_known_names_ok(project: Project) -> None:
    assert rules(project, "from yaml import safe_load, dump, YAMLError\n", '["yaml"]') == []
    assert rules(project, "from hypothesis import given, strategies, settings\n", '["hypothesis"]') == []


def test_aif015_submodule_exists_and_missing(project: Project) -> None:
    assert (
        rules(project, "import hypothesis.strategies\nfrom hypothesis.strategies import integers\n", '["hypothesis"]')
        == []
    )
    errors = run(project, "import hypothesis.nope\n", '["hypothesis"]')
    assert [e["rule"] for e in errors] == ["AIF015"] and "hypothesis.nope" in errors[0]["cause"]


def test_aif015_from_package_import_submodule_ok(project: Project) -> None:
    assert rules(project, "from hypothesis import strategies\n", '["hypothesis"]') == []


def test_aif015_stdlib_name_checked(project: Project) -> None:
    assert rules(project, "from json import loads, not_a_json_fn\n") == ["AIF015"]
    assert rules(project, "from collections import OrderedDict, defaultdict\n") == []


def test_aif015_stdlib_missing_submodule(project: Project) -> None:
    assert rules(project, "import xml.nope\n") == ["AIF015"]
    assert rules(project, "import xml.etree.ElementTree\nfrom xml.etree import ElementTree\n") == []


def test_optional_dependency_inside_try_importerror_is_skipped(project: Project) -> None:
    src = "try:\n    import ujson as json_impl\nexcept ImportError:\n    import json as json_impl\n"
    assert rules(project, src) == []


def test_try_without_importerror_still_checked(project: Project) -> None:
    src = "try:\n    import ujson\nexcept ValueError:\n    pass\n"
    assert rules(project, src) == ["AIF014"]


def test_dynamic_namespace_is_never_guessed(project: Project) -> None:
    # `os` exports platform-specific names through star imports and conditional blocks: must not false-positive
    assert rules(project, "from os import getcwd, sep, path, listdir\n") == []


def test_star_import_of_stdlib_not_flagged(project: Project) -> None:
    assert rules(project, "from os.path import *\n") == []


def test_can_be_disabled(project: Project) -> None:
    set_options(project, check_third_party="false")
    project.write("adapters/a.py", "import requests\nimport nothing_at_all\n")
    assert [e for e in lint.run(project.root, project.cfg) if e["rule"].startswith("AIF01")] == []


def test_relative_imports_untouched(project: Project) -> None:
    project.write("adapters/b.py", "X = 1\n")
    assert rules(project, "from . import b\nfrom .b import X\n") == []


def test_submodule_of_compiled_extension_is_not_guessed(project: Project) -> None:
    assert rules(project, "from hypothesis._native.internal import floats\n", '["hypothesis"]') == []


def test_platform_specific_stdlib_module_not_flagged(project: Project) -> None:
    assert rules(project, "import msvcrt\n") == []


def test_import_under_version_or_platform_check_is_skipped(project: Project) -> None:
    src = "import sys\n\nif sys.version_info < (3, 8):\n    import legacy_backport\n"
    assert rules(project, src) == []


def test_dynamic_namespace_via_globals_is_skipped(tmp_path: Path) -> None:
    from aif import thirdparty

    tree = __import__("ast").parse("globals()['x'] = 1\n")
    assert thirdparty._collect(tree.body, set(), lambda t, lv: None) is False

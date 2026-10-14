from __future__ import annotations

from aif import lint
from tests.framework.conftest import Project

BOX = """class Box:
    size: int = 1

    def __init__(self) -> None:
        self.items: list[int] = []
        self.label = "x"

    def add(self, v: int) -> None:
        self.items.append(v)

    def total(self) -> int:
        return len(self.items)
"""


def rules(project: Project, body: str, prefix: str = "") -> list[str]:
    project.write("adapters/box.py", BOX)
    project.write("adapters/use.py", "from adapters.box import Box\n" + prefix + body)
    return [e["rule"] for e in lint.run(project.root, project.cfg) if e["rule"] == "AIF012"]


def test_param_annotation_unknown_method(project: Project) -> None:
    assert rules(project, "\n\ndef f(b: Box) -> None:\n    b.push(1)\n") == ["AIF012"]


def test_param_annotation_known_members_ok(project: Project) -> None:
    body = "\n\ndef f(b: Box) -> int:\n    b.add(1)\n    return b.size + len(b.items) + len(b.label) + b.total()\n"
    assert rules(project, body) == []


def test_self_unknown_attribute_read(project: Project) -> None:
    project.write("adapters/s.py", BOX + "\n    def bad(self) -> int:\n        return self.missing\n")
    assert [e["rule"] for e in lint.run(project.root, project.cfg)] == ["AIF012"]


def test_self_attribute_defined_later_in_other_method_ok(project: Project) -> None:
    src = (
        "class A:\n    def a(self) -> int:\n        return self.later\n\n"
        "    def b(self) -> None:\n        self.later = 1\n"
    )
    project.write("adapters/s.py", src)
    assert lint.run(project.root, project.cfg) == []


def test_constructor_assignment_infers_type(project: Project) -> None:
    assert rules(project, "\n\ndef f() -> None:\n    b = Box()\n    b.nope()\n") == ["AIF012"]
    assert rules(project, "\n\ndef f() -> int:\n    b = Box()\n    return b.total()\n") == []


def test_rebound_name_is_not_trusted(project: Project) -> None:
    body = "\n\ndef f(x: int) -> None:\n    b = Box()\n    if x:\n        b = object()\n    b.nope()\n"
    assert rules(project, body) == []


def test_loop_and_with_targets_not_trusted(project: Project) -> None:
    body = "\n\ndef f(bs: list[Box]) -> None:\n    for b in bs:\n        b.nope()\n"
    assert rules(project, body) == []


def test_chained_attribute_type(project: Project) -> None:
    src = (
        "from adapters.box import Box\n\n\nclass Holder:\n    box: Box\n\n"
        "    def go(self) -> None:\n        self.box.nope()\n"
    )
    project.write("adapters/box.py", BOX)
    project.write("adapters/h.py", src)
    assert [e["rule"] for e in lint.run(project.root, project.cfg)] == ["AIF012"]


def test_return_type_of_function_and_method(project: Project) -> None:
    body = "\n\ndef make() -> Box:\n    return Box()\n\n\ndef f() -> None:\n    make().nope()\n"
    assert rules(project, body) == ["AIF012"]


def test_optional_and_union_with_none(project: Project) -> None:
    assert rules(project, "\n\ndef f(b: Box | None) -> None:\n    b.nope()\n") == ["AIF012"]
    assert rules(project, "\n\ndef f(b: Optional[Box]) -> None:\n    b.nope()\n", "from typing import Optional\n") == [
        "AIF012"
    ]


def test_containers_are_not_the_element_type(project: Project) -> None:
    assert rules(project, "\n\ndef f(bs: list[Box]) -> None:\n    bs.append(Box())\n") == []


def test_ambiguous_union_is_skipped(project: Project) -> None:
    project.write("adapters/other.py", "class Other:\n    def run(self) -> None: ...\n")
    body = "\n\ndef f(b: Box | Other) -> None:\n    b.run()\n"
    assert rules(project, "from adapters.other import Other\n" + body) == []


def test_inheritance_inherits_members(project: Project) -> None:
    src = (
        "from adapters.box import Box\n\n\nclass Big(Box):\n    pass\n\n\n"
        "def f(b: Big) -> int:\n    return b.total() + b.size\n"
    )
    project.write("adapters/box.py", BOX)
    project.write("adapters/big.py", src)
    assert lint.run(project.root, project.cfg) == []
    project.write("adapters/big.py", src.replace("b.total()", "b.nope()"))
    assert [e["rule"] for e in lint.run(project.root, project.cfg)] == ["AIF012"]


def test_unknown_base_makes_class_opaque(project: Project) -> None:
    project.write(
        "adapters/o.py",
        "from json import JSONEncoder\n\n\nclass E(JSONEncoder):\n    pass\n\n\n"
        "def f(e: E) -> None:\n    e.anything()\n",
    )
    assert lint.run(project.root, project.cfg) == []


def test_getattr_and_setattr_classes_are_opaque(project: Project) -> None:
    src = (
        "class D:\n    def __getattr__(self, n: str) -> int:\n        return 1\n\n\n"
        "def f(d: D) -> int:\n    return d.whatever\n"
    )
    project.write("adapters/d.py", src)
    assert lint.run(project.root, project.cfg) == []


def test_dataclass_fields_are_members(project: Project) -> None:
    src = (
        "from dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass P:\n    x: int\n\n\n"
        "def f(p: P) -> int:\n    return p.x + p.y\n"
    )
    project.write("adapters/p.py", src)
    assert [e["rule"] for e in lint.run(project.root, project.cfg)] == ["AIF012"]


def test_unknown_decorator_makes_class_opaque(project: Project) -> None:
    src = (
        "from functools import cache as magic\n\n\n@magic\nclass M:\n    pass\n\n\n"
        "def f(m: M) -> None:\n    m.anything()\n"
    )
    project.write("adapters/m.py", src)
    assert lint.run(project.root, project.cfg) == []


def test_classmethod_and_staticmethod_first_arg(project: Project) -> None:
    src = (
        "class A:\n    @classmethod\n    def make(cls) -> int:\n        return cls.missing\n\n"
        "    @staticmethod\n    def s(x: int) -> int:\n        return x\n"
    )
    project.write("adapters/a.py", src)
    assert lint.run(project.root, project.cfg) == []  # cls is not an instance: skipped, never a false positive


def test_parameter_rebound_is_dropped(project: Project) -> None:
    body = "\n\ndef f(b: Box) -> None:\n    b = object()\n    b.nope()\n"
    assert rules(project, body) == []

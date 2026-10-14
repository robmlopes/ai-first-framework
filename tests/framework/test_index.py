from __future__ import annotations

from aif import index


def test_index_lists_functions_classes_methods(project):
    project.write(
        "domain/m.py",
        '''from aif import contract


class Box:
    """A box."""

    size: int = 1
    LIMIT = 3

    def open(self, force: bool) -> None:
        pass


@contract(requires=lambda x: x > 0, effects=[])
def f(x: int) -> int:
    """Doc line.

    More.
    """
    return x
''',
    )
    idx = index.generate(project.root, project.cfg)["domain.m"]
    assert idx["f"]["kind"] == "function"
    assert idx["f"]["args"] == ["x: int"]
    assert idx["f"]["returns"] == "int"
    assert idx["f"]["doc"] == "Doc line."
    assert idx["f"]["contract"]["effects"] == "[]"
    assert idx["Box"]["kind"] == "class"
    assert idx["Box"]["attributes"] == ["size", "LIMIT"]
    assert idx["Box"]["methods"]["open"]["args"] == ["force: bool"]
    assert idx["Box"]["methods"]["open"]["kind"] == "method"


def test_package_init_maps_to_package_name(project):
    assert "domain" in index.generate(project.root, project.cfg)


def test_save_writes_json(project):
    index.save(project.root, project.cfg)
    assert (project.root / ".aif" / "index.json").is_file()

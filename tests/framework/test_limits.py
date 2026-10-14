from __future__ import annotations

from aif import lint
from tests.framework.conftest import Project


def run(project: Project) -> list[dict[str, object]]:
    return lint.run(project.root, project.cfg)


def func(lines: int, name: str = "f") -> str:
    body = "\n".join(f"    x{i} = {i}" for i in range(lines))
    return f"def {name}() -> None:\n{body}\n"


def with_toml(project: Project, extra: str) -> None:
    project.write("aif.toml", project.root.joinpath("aif.toml").read_text() + extra)


def test_blank_comment_and_docstring_lines_do_not_count(project: Project) -> None:
    body = "\n".join(f"    x{i} = {i}\n\n    # note" for i in range(30))
    doc = '    """Docs.\n\n    More docs.\n    """\n'
    project.write("adapters/a.py", f"def f() -> None:\n{doc}{body}\n")
    assert run(project) == []  # 61+ physical lines, only 31 of code


def test_physical_lines_when_code_line_counting_is_off(project: Project) -> None:
    with_toml(project, "\n")
    project.write(
        "aif.toml",
        project.root.joinpath("aif.toml").read_text().replace("[aif]\n", "[aif]\ncount_code_lines = false\n", 1),
    )
    body = "\n".join(f"    x{i} = {i}\n" for i in range(25))
    project.write("adapters/a.py", f"def f() -> None:\n{body}\n")
    assert project.rules(run(project)) == ["AIF005"]


def test_per_layer_limit_override(project: Project) -> None:
    project.write(
        "aif.toml",
        project.root.joinpath("aif.toml")
        .read_text()
        .replace("[aif.capabilities]", "[aif.limits.adapters]\nmax_function_lines = 80\n\n[aif.capabilities]"),
    )
    project.write("adapters/a.py", func(60))
    assert run(project) == []
    project.write("domain/m.py", "from aif import contract\n\n\n@contract(effects=[])\n" + func(60, "g"))
    assert "AIF005" in project.rules(run(project))  # domain keeps the global 40


def test_error_names_largest_blocks(project: Project) -> None:
    body = "\n".join(f"        x{i} = {i}" for i in range(45))
    project.write("adapters/a.py", f"def f(a: bool) -> None:\n    if a:\n{body}\n")
    (err,) = run(project)
    assert "if at line 2" in str(err["suggestion"]) and "code lines" in str(err["cause"])


def test_warning_near_limit_is_not_an_error(project: Project) -> None:
    project.write("adapters/a.py", func(37))  # 38 code lines of 40 = 95%
    assert run(project) == []
    from aif import limits

    (warn,) = limits.warnings(project.root, project.cfg)
    assert warn["severity"] == "warning" and warn["rule"] == "AIF005"


def test_no_warning_well_below_limit(project: Project) -> None:
    from aif import limits

    project.write("adapters/a.py", func(10))
    assert limits.warnings(project.root, project.cfg) == []


def test_file_limit_error_names_the_biggest_definitions(project: Project) -> None:
    small = "def small() -> int:\n    return 1\n\n\n"
    big = func(120, "big_one") + "\n\n" + func(100, "next_big")
    project.write("adapters/a.py", small + big)
    errors = [e for e in run(project) if "file has" in str(e["cause"])]
    assert len(errors) == 1
    hint = str(errors[0]["suggestion"])
    assert "big_one (" in hint and "next_big (" in hint and hint.index("big_one") < hint.index("next_big")
    assert "small (" in hint

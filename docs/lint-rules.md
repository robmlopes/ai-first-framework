# Lint rules

Every error is a dict: `{"stage", "rule", "file", "line", "cause", "suggestion"}`.

| Rule | Stage | Applies to | Description | Fix |
|---|---|---|---|---|
| AIF001 | lint | `pure_dirs` | Import of a module in `forbidden_imports` | Receive the effect via a port |
| AIF002 | lint | `pure_dirs` | Public top-level function without `@contract` | Add `@contract(...)` |
| AIF003 | lint | all | Missing parameter or return type hints | Annotate everything |
| AIF004 | lint | all | Bare `except:` or `except Exception` | Catch a specific error |
| AIF005 | lint | all | File longer than `max_file_lines` or function longer than `max_function_lines` | Split |
| AIF006 | lint | all | `from x import y` (absolute or relative) or `import x.y` of a project module/symbol not present in the index; relative imports that climb past the root | Use a name from the suggestion list |
| AIF007 | lint | all | Use of `global` | Pass state as a parameter |
| AIF008 | effects | contracts | Declared effect not defined in `[aif.capabilities]` | Use a valid effect |
| AIF009 | effects | contracts | Effects and received capabilities do not match. Capabilities are recognised through import aliases (`as`), module aliases, simple assignments, unions, generics and quoted annotations | Align `effects=` with parameters |
| AIF010 | effects | `pure_dirs` | Direct call or **reference** (`f = open`, `map(os.path.abspath, xs)`) of a name in `forbidden_calls` (`open`, `getattr`...), including `builtins.open()`, aliases (`reader = open`) and calls into forbidden modules (`os.getcwd()`, `from os import getcwd as g`) | Use an injected port |
| AIF013 | effects | `pure_dirs` | Dynamic dispatch: call through a name bound at runtime (`fn = pick(); fn()`), a subscript (`table[k]()`), a call result (`make()()`) or a loop variable | Call a named function or inject the behaviour as a port |
| AIF011 | effects | `pure_dirs` | Domain imports an effects layer, or reaches I/O through a port module | Invert the dependency |
| AIF012 | lint | all | Unknown member on a project class (`Cls.x`) or on an instance whose class is inferred (`obj.x`): see below | Use a name from the suggestion list |

## Examples

AIF009 - missing declaration:

```python
@contract(effects=[])
def save(x: Account, db: DbWrite) -> None: ...  # needs effects=["db.write"]
```

AIF012 - hallucinated member:

```python
SqliteDb.store  # unknown member: available members: ['__init__', 'close', 'get', 'save']
```

AIF006 - hallucinated name:

```python
from domain.transfer import transfer_all  # unknown symbol: available: ['Account', 'transfer', ...]
```

## How AIF012 infers instance types

A name is trusted only when its class is certain:

| Source | Example |
|---|---|
| `self` in a method | `self.missing` |
| Parameter annotation (also `X \| None`, `Optional[X]`, quoted) | `def f(b: Box): b.push()` |
| Constructor call assigned **once** | `b = Box(); b.push()` |
| Return annotation of a project function or method | `make().push()` |
| Attribute annotation chain | `self.box.push()` (field `box: Box`) |

Members include class attributes, methods, `self.x = ...` assignments in any method and inherited members (project bases). To avoid false positives the check is **skipped** when: the name is re-bound, is a loop/`with`/`except` target, or a parameter that is reassigned; the annotation is ambiguous (`A | B`) or a container (`list[X]`); the class (or any base) is not a project class, has an unknown decorator or class keyword, or defines `__getattr__`/`__getattribute__`/`__slots__`/`setattr`; or the first argument of a `classmethod`.

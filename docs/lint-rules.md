# Lint rules

Every error is a dict: `{"stage", "rule", "file", "line", "cause", "suggestion"}`.

| Rule | Stage | Applies to | Description | Fix |
|---|---|---|---|---|
| AIF001 | lint | `pure_dirs` | Import of a module in `forbidden_imports` | Receive the effect via a port |
| AIF002 | lint | `pure_dirs` | Public top-level function without `@contract` | Add `@contract(...)` |
| AIF003 | lint | all | Missing parameter or return type hints | Annotate everything |
| AIF004 | lint | all | Bare `except:` or `except Exception` | Catch a specific error |
| AIF005 | lint | all | File longer than `max_file_lines` or function longer than `max_function_lines` | Split |
| AIF006 | lint | all | `from <project module> import <symbol>` not present in the index | Use a name from the suggestion list |
| AIF007 | lint | all | Use of `global` | Pass state as a parameter |
| AIF008 | effects | contracts | Declared effect not defined in `[aif.capabilities]` | Use a valid effect |
| AIF009 | effects | contracts | Effects and received capabilities do not match | Align `effects=` with parameters |
| AIF010 | effects | `pure_dirs` | Direct call of a name in `forbidden_calls` (`open`, `print`...) | Use an injected port |
| AIF011 | effects | `pure_dirs` | Domain imports an effects layer, or reaches I/O through a port module | Invert the dependency |
| AIF012 | lint | all | `Class.member` where `Class` is a project class and `member` is not one of its methods or attributes | Use a name from the suggestion list |

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

# CLI

```
python -m aif <command> [--json] [--root PATH]
```

| Command | Action |
|---|---|
| `index` | Writes `.aif/index.json` |
| `patch FILE SYMBOL` | Replaces one top-level function or class (see below) |
| `intent new\|list\|commit-msg` | Manage and validate intents (see below) |
| `fix` | Applies canonical formatting and safe autofixes (ruff), returns what remains |
| `check` | Index -> style (ruff) -> intents -> lint/effects -> types (mypy) -> tests. Exit code 0 when ok, 1 otherwise |

`--root` defaults to the current directory.

## JSON output (`check --json`)

```json
{
  "ok": false,
  "errors": [ ... ]
}
```

### Lint / effects error

```json
{"stage": "lint", "rule": "AIF004", "file": "domain/x.py", "line": 12,
 "cause": "generic except", "suggestion": "catch a specific typed error"}
```

`stage` is `lint` or `effects`.

### Contract violation (from tests)

```json
{
  "stage": "tests",
  "test": "tests.test_transfer::test_transfer_conserves_money",
  "cause": "contract violated",
  "kind": "postcondition",
  "function": "domain.transfer.transfer",
  "counterexample": {"inputs": {"...": "..."}, "result": "..."}
}
```

### Other test failure

```json
{"stage": "tests", "test": "...", "cause": "<first 300 chars of the message>"}
```

### Runner failure

```json
{"stage": "tests", "cause": "pytest did not run", "detail": "<last 800 chars>"}
```

### Type error (mypy)

```json
{"stage": "types", "rule": "return-value", "file": "adapters/sqlite_db.py", "line": 36,
 "cause": "Incompatible return value type (got \"SqliteDb\", expected \"DbWrite\")",
 "suggestion": "returned value does not match the declared type; ..."}
```

`rule` is the mypy error code. Stages run in order (style, intents, lint/effects, types, tests); each runs only if the previous passed.

## `aif patch`

Replaces a single top-level function, class or method instead of rewriting the file.

```bash
python -m aif patch domain/transfer.py persist --from new_persist.py   # or pipe via stdin
python -m aif patch domain/transfer.py persist --dry-run < new.py      # diff only
python -m aif patch adapters/sqlite_db.py SqliteDb.get < new_get.py    # a method: Class.method
```

| Flag | Meaning |
|---|---|
| `--from PATH` | File holding the new definition (default: stdin) |
| `--dry-run` | Return the diff without writing |
| `--keep` | Keep the change even if lint/effects fail (default: roll back) |

Rules:

- The new source must be exactly one function/class with the **same name**, decorators included. For `Class.method`, send just the method (any indentation; it is re-indented to fit the class). A method patch must be a function, not a class.
- The target must be a `.py` file inside `source_dirs` (path traversal is rejected).
- After writing, lint and effects rules run on the whole project. Any error rolls the file back and is returned with `"rolled_back": true`.
- Tests are not run by `patch`; run `aif check --json` afterwards.

Output: `{"ok", "file", "symbol", "lines_replaced": [start, end], "diff", "errors"}`; on failure `{"ok": false, "stage": "patch", "cause", "suggestion"}`.

### Style error (ruff)

```json
{"stage": "style", "rule": "format", "file": "domain/x.py", "line": 1,
 "cause": "file is not in canonical format", "suggestion": "run `python -m aif fix`"}
```

`rule` is `format` (ruff format) or a ruff code (`F401`, `E402`...). Fixable errors suggest `aif fix`.

## `aif intent`

```bash
python -m aif intent new money-transfer Transfer money safely   # creates .aif/intents/money-transfer.md from a template
python -m aif intent list                                       # id, title, scope of every intent
python -m aif intent commit-msg .git/COMMIT_EDITMSG             # validate the Intent trailer
```

Intents live in `.aif/intents/<id>.md` (kebab-case id). Required format:

```markdown
# <title>

## Why
<human reason, non-empty>

## Scope
- domain/transfer.py        <- every path must exist

## Acceptance
- <observable behaviour>
```

| Rule | Meaning |
|---|---|
| INT001 | Intent id is not kebab-case |
| INT002 | Missing title or an empty `Why` / `Scope` / `Acceptance` section |
| INT003 | A path in `Scope` does not exist |
| INT004 | Commit message has no `Intent: <id>` trailer |
| INT005 | Commit trailer names an unknown intent |

Intent errors use `"stage": "intents"`. `aif check` validates all intents (INT001-INT003); INT004/INT005 apply to commit messages via `scripts/commit-msg`, which you install as a git `commit-msg` hook.

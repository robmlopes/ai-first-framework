# CLI

```
aif <command> [--json] [--root PATH]      # same as: python -m aif ...
```

| Command | Action |
|---|---|
| `index` | Writes `.aif/index.json` |
| `patch FILE SYMBOL` | Replaces one top-level function or class (see below) |
| `intent new\|list\|commit-msg` | Manage and validate intents (see below) |
| `agents` | Regenerates `AGENTS.md`, `CLAUDE.md` and `.cursor/rules/aif.mdc` from `.aif/protocol.md` |
| `fix` | Applies canonical formatting and safe autofixes (ruff), returns what remains |
| `check` | Index -> style (ruff) -> agent files -> intents -> lint/effects -> types (mypy) / fuzz / tests (run concurrently). Exit code 0 when ok, 1 otherwise. Options: `--changed`, `--background` |
| `status` | Prints `.aif/last-check.json`; exit 0 when the last check passed, 3 while one is running, 1 otherwise |
| `docs` | Checks that `docs/` agrees with the code: rules, config options, CLI commands, links (DOC001-DOC004) |
| `stats` | Summarises `.aif/history.jsonl`: runs, attempts before ok, rules that fire most, time per stage |

`--root` defaults to the current directory.

## `aif check` options

| Option | Effect |
|---|---|
| `--changed` | Style and lint look only at files that differ from `HEAD` (modified, staged, untracked). Types, fuzz and tests still cover everything, because a change can break a file it did not touch. Fuzz is cached per module, so unchanged modules are skipped in every mode. Outside a git repository it checks everything. |
| `--background` | Starts the check detached and returns at once. Poll with `aif status`; the result is `.aif/last-check.json`. Use it when your tool has a timeout shorter than the pipeline. |

Plain `aif check` also uses the fuzz cache and runs mypy, fuzz and pytest in parallel (`parallel = false` to disable). The cache key of a module covers its source, every project module it imports, the fuzz settings, the `fuzz_setup` module and the framework's fuzz code; a failing module is never cached. The cache lives in `.aif/cache/` (gitignored).

## JSON output (`check --json`)

```json
{
  "ok": false,
  "errors": [ ... ],
  "warnings": [ ... ],
  "timings": {"index": 0.0, "style": 0.4, "lint": 0.3, "types": 6.1, "fuzz": 2.0, "tests": 3.2, "total": 6.3},
  "changed_only": ["domain/x.py"]
}
```

`warnings` holds AIF005 entries (`"severity": "warning"`) for functions and files at 90% or more of their limit (`limit_warn_ratio`); they never fail the check. `timings` are seconds per stage; `types`, `fuzz` and `tests` overlap when `parallel = true`, so `total` is less than their sum. `changed_only` appears only with `--changed`.

## Run history

Every `aif check` appends one line to `.aif/history.jsonl` (gitignored; `history = false` disables it): outcome, which rules fired, timings. `aif stats` summarises it, including **attempts before ok** (failing runs between successes), which is the measure of how much feedback an agent needed.

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

`rule` is the mypy error code. Stages run in order (style, agents, intents, lint/effects, types, tests); each runs only if the previous passed.

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
| INT006 | A staged file is not listed in the cited intent's `Scope` (docs/, tests/, `.aif/`, root files and empty `__init__.py` are exempt) |

Intent errors use `"stage": "intents"`. `aif check` validates all intents (INT001-INT003); INT004-INT006 apply to commit messages via `scripts/commit-msg`, which you install as a git `commit-msg` hook.

## `aif upgrade`

Brings a project up to date after you install a newer AIF. Without `--apply` it only reports; nothing is written.

```
aif upgrade            # what is out of date
aif upgrade --apply    # update it
```

| Updated by `--apply` | How |
|---|---|
| `.aif/protocol.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/aif.mdc` | replaced with the current versions |
| git hooks | reinstalled when they differ |
| `.gitignore` | missing AIF entries are appended; your lines stay |
| `aif.toml` | options the current template defines and you do not set are added with their defaults under a `# added by aif upgrade` comment; **your values are never changed** |

`manual` lists what needs your decision and is never edited, for example a `forbidden_imports` that still bans `datetime`. Run `aif check --json` afterwards.

## Project environment

`check`, `fix`, `fuzz`, `index` and `patch` run project code and tools, so they need the project's dependencies. When the project has a `.venv` (or `venv`) and `aif` was started from another interpreter (pipx, system Python), `aif` re-runs itself with the project's interpreter automatically. Without that, AIF014 would report every declared package as "not installed". If no project environment exists, the hint on the error names the interpreter that was used.

## `aif docs`

Verifies the documentation by machine, so "are the docs up to date?" has a checkable answer. It also runs as a stage of `aif check` when `docs_check = true` (off by default: the rules compare `docs/` against the AIF framework, so only the AIF repository enables it). Silent for projects without a `docs/` directory.

| Rule | Fails when |
|---|---|
| DOC001 | a rule id the code can emit appears nowhere in `docs/`, or a documented id is never emitted |
| DOC002 | a `Config` option is missing from `docs/configuration.md` |
| DOC003 | a CLI command is missing from `docs/cli.md` |
| DOC004 | a relative Markdown link in `README.md` or `docs/*.md` points to a missing file or heading |

## `aif init [DIR]`

Creates a new AIF project in `DIR` (default `--root`; `--profile web-api` or `--profile cli` adds an entry layer, see below): `aif.toml`, `pyproject.toml`, `.gitignore`, `.aif/protocol.md`, a `bootstrap` intent, empty `domain/ ports/ adapters/ tests/` packages, `tests/strategies.py`, the hook scripts and the generated agent files. It runs `git init` and installs the hooks unless `--no-git` is given, never overwrites existing files, and refuses a directory that already has an `aif.toml`. The result passes `aif check` immediately. Templates live in `aif/templates/`.

### Profiles

| Profile | Adds |
|---|---|
| `web-api` | `web/` entry layer with a FastAPI `create_app()` composition root and a `/health` test; `fastapi` in `third_party`; `fastapi` and `httpx` in the `dev` extra; `[aif.limits.web] max_function_lines = 60` |
| `cli` | `cli/` entry layer with an argparse `main()` composition root and a test; `[aif.limits.cli] max_function_lines = 60` |

Both profiles set `entry_dirs` and `composition_roots`, so adapters are wired only in `main.py` (AIF016), and both add the new files to the bootstrap intent's scope. The project passes `aif check` and the first commit straight away.

## `aif fuzz`

Runs only the contract-fuzzing stage and prints `{"ok", "errors"}` (see `contracts.md`, rules CON001-CON005). Useful while iterating on a contract, because the full pipeline takes longer.

`aif fuzz --report` ignores the cache and prints what was covered:

```json
{
  "ok": true,
  "tested": [{"module": "domain.pricing", "function": "discounted", "status": "passed", "examples": 100,
              "bounds_from_requires": {"price": [0, null], "percent": [0, 100]}, "custom_strategies": []}],
  "skipped": [{"module": "domain.store", "function": "store", "reason": "declares effects: needs real ports, covered by integration tests"}],
  "summary": {"functions_fuzzed": 1, "examples_run": 100, "failed": 0, "skipped": 1, "skipped_by_reason": {"...": 1}}
}
```

`status` is `passed`, `failed` or `not-generated` (CON003). Skip reasons: no `@contract`, no `ensures`, declared effects. Private helpers (`_name`) without a contract are not listed. Fuzzing checks properties of pure functions on sampled inputs; it does not test concurrency or integration with real ports.

## `aif agents`

`.aif/protocol.md` is the single source of the agent protocol. `aif agents` renders it into `AGENTS.md` (generic agents), `CLAUDE.md` (Claude Code) and `.cursor/rules/aif.mdc` (Cursor). `aif check` fails with `AGT001` (`stage: "agents"`) when a generated file is missing or differs from the source; fix with `aif agents`. Edit the protocol only in `.aif/protocol.md`.

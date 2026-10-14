# Workflow: hooks, CI and tests

## Git hooks

```bash
sh scripts/install-hooks.sh
```

| Hook | Script | Blocks the commit when |
|---|---|---|
| `pre-commit` | `scripts/pre-commit` | `aif check` fails (style, intents, lint, types or tests) |
| `commit-msg` | `scripts/commit-msg` | no `Intent: <id>` trailer (INT004), unknown intent (INT005), or a staged file outside the intent's `Scope` (INT006) |

Set `PYTHON=/path/to/python` if the hooks must use a specific interpreter. One commit = one intent: when a change touches files from several intents, split it into several commits.

Example accepted message:

```
feat: add transfer domain

Intent: money-transfer
```

## CI

`.github/workflows/aif.yml` installs the package (`pip install -e ".[dev]"`), runs `aif check --json` (uploaded as the `aif-report-<version>` artifact) and the framework tests on a matrix of Python 3.11, 3.12 and 3.13. The matrix matters: 3.11 is the declared minimum, and an `ast.TypeAlias` reference (3.12+ only) once passed locally on 3.12 but broke 105 tests in CI on 3.11. Keep the code importable on the minimum version.

## Tests

| Path | Covers |
|---|---|
| `tests/` | The example project (transfer domain, SQLite adapter) |
| `tests/framework/` | The framework itself: every rule, CLI command, patch, intents, style and types stages, using throwaway projects in `tmp_path` |

`aif check` runs all of `tests/`, including `tests/framework/`.

## Generated files

`.aif/index.json` is regenerated on every check and is **not** versioned (listed in `.gitignore`).

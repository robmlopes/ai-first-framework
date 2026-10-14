# Configuration (`aif.toml`)

All keys live under `[aif]`. Unknown keys are ignored; missing keys use defaults.

| Key | Default | Meaning |
|---|---|---|
| `source_dirs` | `["domain"]` | Directories scanned, indexed and linted |
| `pure_dirs` | `["domain"]` | Layers with no I/O and mandatory `@contract` |
| `port_dirs` | `["ports"]` | Layers that hold effect interfaces only |
| `max_file_lines` | `200` | AIF005 file limit |
| `max_function_lines` | `40` | AIF005 function limit |
| `intents` | `true` | Validate `.aif/intents/*.md` during `aif check` |
| `style` | `true` | Run ruff format check + ruff check over `source_dirs` and `tests` |
| `typecheck` | `true` | Run mypy over `source_dirs` as a pipeline stage |
| `typecheck_tests` | `true` | Also type-check `tests/` |
| `mypy_args` | `["--strict"]` | Extra mypy arguments |
| `forbidden_imports` | `[]` | Top-level modules banned in `pure_dirs` (AIF001) and treated as I/O by AIF011 |
| `forbidden_calls` | `open, print, input, exec, eval, compile, __import__, getattr, setattr` | Names banned in `pure_dirs` (AIF010), also when reached via `builtins.` or an alias |

## `[aif.capabilities]`

Maps a capability type name to the effects it grants:

```toml
[aif.capabilities]
DbWrite = ["db.write"]
HttpGet = ["net.read"]
```

Adding a new effect is a two-step change: add the port Protocol in `ports/`, then register its type here.

## Environment

| Variable | Effect |
|---|---|
| `AIF_CONTRACTS=off` | Disables runtime contract checks (production) |

Ruff itself is configured in `pyproject.toml` under `[tool.ruff]` (line length 120, rules E, F, I, B, UP, SIM).

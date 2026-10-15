# Configuration (`aif.toml`)

All keys live under `[aif]`. Unknown keys are ignored; missing keys use defaults.

| Key | Default | Meaning |
|---|---|---|
| `source_dirs` | `["domain"]` | Directories scanned, indexed and linted |
| `pure_dirs` | `["domain"]` | Layers with no I/O and mandatory `@contract` |
| `port_dirs` | `["ports"]` | Layers that hold effect interfaces only |
| `max_file_lines` | `200` | AIF005 file limit |
| `max_function_lines` | `40` | AIF005 function limit |
| `limits` | `{}` | Per-layer overrides: `[aif.limits.web]` with `max_function_lines` / `max_file_lines` (see below) |
| `count_code_lines` | `true` | AIF005 ignores blank lines, comments and docstrings |
| `limit_warn_ratio` | `0.9` | Share of a limit at which a non-failing warning appears |
| `entry_dirs` | `[]` | Entry layers such as `web`; added to `source_dirs`, not pure, may use domain and ports (AIF016) |
| `adapter_dirs` | `["adapters"]` | Layers that entry layers must not import directly |
| `composition_roots` | `[]` | Modules in `entry_dirs` allowed to import adapters (e.g. `["web.main"]`) |
| `forbidden_clock` | `datetime.datetime.now`, `time.time`, `time.sleep`, ... | Clock reads banned in `pure_dirs` (AIF010); date/time types stay allowed |
| `parallel` | `true` | Run mypy, fuzz and pytest concurrently |
| `docs_check` | `false` | `aif check` also verifies that `docs/` agrees with the AIF framework's own rules, options and commands (DOC001-DOC004). Meant for the AIF repository itself: leave it off in application projects |
| `history` | `true` | Append every check to `.aif/history.jsonl` |
| `intents` | `true` | Validate `.aif/intents/*.md` during `aif check` |
| `style` | `true` | Run ruff format check + ruff check over `source_dirs` and `tests` |
| `typecheck` | `true` | Run mypy over `source_dirs` as a pipeline stage |
| `typecheck_tests` | `true` | Also type-check `tests/` |
| `third_party` | `[]` | Top-level import names of third-party packages that `source_dirs` may import (AIF014) |
| `check_third_party` | `true` | Enable AIF014/AIF015 |
| `fuzz` | `true` | Property-check every `@contract(ensures=...)` from type hints (CON001-CON005) |
| `fuzz_examples` | `100` | Generated inputs per function |
| `fuzz_finite_numbers` | `true` | Generate only finite floats/decimals |
| `fuzz_setup` | `""` | Module that registers domain input strategies (e.g. `tests.strategies`) |
| `mypy_args` | `["--strict"]` | Extra mypy arguments |
| `forbidden_imports` | `[]` | Top-level modules banned in `pure_dirs` (AIF001) and treated as I/O by AIF011 |
| `forbidden_calls` | `open, print, input, exec, eval, compile, __import__, getattr, setattr` | Names banned in `pure_dirs` (AIF010), also when reached via `builtins.` or an alias |

## `[aif.limits.<layer>]`

```toml
[aif.limits.web]
max_function_lines = 60     # route handlers are naturally longer than domain functions
```

A layer not listed uses the global `max_file_lines` / `max_function_lines`.

## Layers for web and CLI code

```toml
[aif]
source_dirs = ["domain", "ports", "adapters"]
entry_dirs = ["web"]
composition_roots = ["web.main"]
```

`web/` may import `domain` and `ports`. Importing `adapters` from any other module of `web/` is AIF016: handlers receive ports as parameters and only `web/main.py` (the composition root) builds the adapters. Entry layers may do I/O, so they are not `pure_dirs`.

## Time in pure code

`datetime`, `date`, `time` and `timedelta` are ordinary types and may appear in `domain/` (for example `d + timedelta(days=1)`). What is banned is *reading the clock*: `datetime.now()`, `date.today()`, `time.time()` and the rest of `forbidden_clock` (AIF010). Inject a `Clock` port instead; `aif init` creates `ports/clock.py`.

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

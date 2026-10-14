# Architecture

## Principles

1. **Restricted language subset.** One canonical form per construct, enforced by lint. No metaprogramming, no dynamic imports, no magic `*args`.
2. **Small, self-contained modules.** Each file fits in a context window together with its contracts (`max_file_lines`, `max_function_lines`).
3. **Contract next to every function.** Preconditions, postconditions and declared effects.
4. **Effects only through injected capabilities.** No `open()`, `requests.get()` or `os.environ` in the domain.
5. **Machine-readable project map.** `.aif/index.json` lets the AI query what exists instead of guessing names.
6. **One verification command** returning structured JSON.
7. **Small atomic changes.** Surgical patches, not file rewrites.

## Layers (hexagonal architecture)

```
domain/   pure logic, no I/O, @contract required
   |  depends on
ports/    interfaces of effects (typing.Protocol), no implementations
   ^  implemented by
adapters/ real implementations (DB, HTTP, filesystem...)
```

### Dependency rules

| From | May import | Must not import |
|---|---|---|
| `domain/` | `domain/`, `ports/`, stdlib not in `forbidden_imports` | `adapters/`, any I/O module |
| `ports/` | `domain/` (types only, under `TYPE_CHECKING`) | `adapters/`, I/O modules |
| `adapters/` | `ports/`, `domain/`, I/O libraries | - |

Violations are reported by AIF001, AIF006 and AIF011. Indirect paths (`domain -> ports -> adapters`) are followed through the import graph.

## Capabilities

A capability is a port type received as a parameter. `aif.toml` maps each capability type to the effects it grants:

```toml
[aif.capabilities]
DbWrite = ["db.write"]
```

A function that takes `db: DbWrite` must declare `effects=["db.write"]`, and vice versa (AIF009). Unknown effect names fail (AIF008).

## Verification pipeline

`aif check` runs, in order, and stops at the first failing stage:

1. Regenerate the index
2. Style (ruff format + ruff check): one canonical form
3. Agent files up to date (AGT001)
4. Intents (`.aif/intents/*.md` well-formed, scope paths exist)
5. Lint + effects (AST rules)
6. Types (mypy `--strict` over `source_dirs`); also checks adapters against port Protocols
7. Tests (pytest + Hypothesis); contract violations become structured counterexamples

## Worked example: domain -> port -> adapter

```
domain/transfer.py   persist(result, db: DbWrite)   effects=["db.write"]
ports/db.py          class DbWrite(Protocol): save(account)
adapters/sqlite_db.py class SqliteDb: save(account), get(id)   # uses sqlite3
```

The domain never imports `sqlite3` or `SqliteDb`. The caller (composition root or test) builds `SqliteDb()` and injects it into `persist`. `SqliteDb` satisfies `DbWrite` structurally (no inheritance). Balances are stored as `TEXT` so `Decimal` values round-trip exactly. `tests/test_sqlite_db.py` runs the full flow with Hypothesis.

Port conformance is verified by mypy: `adapters/sqlite_db.py` ends with `as_db_write(db: SqliteDb) -> DbWrite`, which fails type-checking if `SqliteDb` stops satisfying the `DbWrite` Protocol.

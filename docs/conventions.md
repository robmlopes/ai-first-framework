# Conventions

## Language

All code, identifiers, comments, docstrings, error messages, JSON keys, configuration and documentation are written in **English**. This includes `@contract` keyword arguments (`requires`, `ensures`, `effects`).

## Naming

| Item | Style | Example |
|---|---|---|
| Modules / files | `snake_case`, singular noun | `transfer.py` |
| Functions | `snake_case`, verb first | `transfer`, `persist` |
| Classes / Protocols | `PascalCase` | `Account`, `DbWrite` |
| Effects | `<resource>.<action>` | `db.write`, `net.read` |
| Capability types | `<Resource><Action>` | `DbWrite` |
| Lint rules | `AIF` + 3 digits | `AIF009` |

## Code

- Full type hints on every function.
- Typed errors only; never `except Exception`.
- No global mutable state.
- Immutable data (`@dataclass(frozen=True)`) in the domain.
- Files <= 200 lines, functions <= 40 lines (configurable).
- Docstring first line is indexed: make it a one-sentence summary.

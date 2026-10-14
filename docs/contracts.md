# Contracts

```python
from aif import contract


@contract(
    requires=lambda source, amount: amount > 0 and source.balance >= amount,
    ensures=lambda r, source, target: r.source.balance + r.target.balance == source.balance + target.balance,
    effects=[],
)
def transfer(source: Account, target: Account, amount: Decimal) -> TransferResult: ...
```

## Arguments (all keyword-only)

| Argument | Meaning |
|---|---|
| `requires` | Precondition. Lambda may name only the parameters it uses. |
| `ensures` | Postcondition. First parameter is the result; the rest are inputs by name. |
| `effects` | List of declared effects. `[]` means pure. |

## Runtime behaviour

- Checked on every call unless `AIF_CONTRACTS=off`.
- A violation raises `ContractViolation` with attributes `kind` (`precondition` / `postcondition`), `function` and `counterexample` (`inputs`, and `result` for postconditions).
- The message embeds JSON prefixed with `AIF_CONTRACT`, which `aif check` parses into a structured error.
- The decorated function exposes `__aif__ = {"effects": [...]}`.

## Effects and capabilities

```python
@contract(effects=["db.write"])
def persist(result: TransferResult, db: DbWrite) -> None: ...
```

The effect `db.write` is granted by the `DbWrite` capability type (see `[aif.capabilities]`). The linter requires declared effects and received capabilities to match exactly.

## Writing good contracts

- Postconditions should express invariants (conservation, ordering, bounds), not restate the implementation.
- Property tests (Hypothesis) exercise contracts; a contract never run by a test proves nothing.
- A wrong contract produces "correct" code that does the wrong thing: review contracts as carefully as code.

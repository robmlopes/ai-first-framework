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

## Typing of `@contract`

`contract` is generic over the decorated function (`F -> F`), so decorated functions keep their signature for mypy, and the package ships `py.typed`, so projects that install `aif` get `mypy --strict` without `Untyped decorator` errors.

## Automatic contract fuzzing (`aif fuzz` stage)

Contracts are no longer only as strong as the tests that happen to call them. After lint and types pass, `aif check` property-tests **every** `@contract(ensures=...)` in `source_dirs`:

- inputs are generated from the type hints with Hypothesis (`from_type`); floats and decimals are finite by default (`fuzz_finite_numbers`);
- inputs that violate `requires` are discarded; `ensures` is checked on the rest;
- the run is deterministic (`derandomize`), so the same code gives the same verdict;
- functions that declare `effects` are skipped (they need real ports), as are contracts with no `ensures`.

Rules (`stage: "fuzz"`):

| Rule | Meaning | Fix |
|---|---|---|
| CON001 | `ensures` failed for inputs satisfying `requires`; `counterexample` has inputs and result | Fix the implementation or the clause |
| CON002 | The function raised for inputs satisfying `requires` | Tighten `requires` or handle the input |
| CON003 | Inputs cannot be generated (unannotated parameter, unsupported type) | Annotate, or pass `strategies=` |
| CON004 | `requires` rejected (almost) every input | Relax `requires` or pass `strategies=` |
| CON005 | The fuzz worker itself failed (e.g. a module cannot be imported) | Fix the import error shown |

### Ranges inferred from `requires`

Integer and float parameters are narrowed automatically from simple comparisons in `requires` joined by `and`: `price >= 0 and 0 <= percent <= 100` generates `price` in `[0, inf)` and `percent` in `[0, 100]`, and `x == 123456` hits that value every time. Strict bounds are tightened (`x > 5` becomes `x >= 6`). Anything else (`or`, `len(s) > 0`, comparisons between parameters) is ignored: the predicate still filters afterwards, and `strategies=` can override. A contradictory range such as `x > 5 and x < 3` is reported as CON004.

### Controlling the input space

```python
from hypothesis import strategies as st

@contract(
    requires=lambda amount: amount > 0,
    ensures=lambda r, amount: r >= amount,
    strategies={"amount": st.integers(1, 10_000)},   # per-parameter override
)
```

Domain types can be registered once in the module named by `fuzz_setup` (here `tests/strategies.py`: money is a `Decimal` with two places and a bounded magnitude). The fuzzer found that unbounded `Decimal` inputs overflow the 28-digit context, which is a real property of the domain that the strategy now encodes explicitly.

Fuzzing runs in a subprocess; set `fuzz = false` to turn it off, `fuzz_examples` to change the budget (default 100 per function).

# Project structure

```
project/
├── .github/workflows/aif.yml # CI
├── aif.toml                  # rules, limits, allowed capabilities
├── AGENTS.md, CLAUDE.md      # generated agent instructions (do not edit)
├── .cursor/rules/aif.mdc     # generated, for Cursor
├── pyproject.toml            # packaging and pytest config
├── .aif/
│   ├── protocol.md           # single source of the agent protocol
│   ├── index.json            # generated map: modules, functions, signatures, contracts
│   └── intents/              # human intent per feature - the "why"
│       └── money-transfer.md # example intent
├── aif/                      # the framework itself
│   ├── __init__.py           # exports contract, ContractViolation
│   ├── __main__.py           # python -m aif entry point
│   ├── cli.py                # `aif check` / `aif index` orchestration
│   ├── config.py             # aif.toml loader (Config dataclass)
│   ├── contract.py           # @contract decorator and ContractViolation
│   ├── index.py              # AST -> index.json generator
│   ├── lint.py               # rules AIF001-AIF007, AIF012
│   ├── agents.py             # generates agent instruction files
│   ├── intents.py            # intent parsing, validation, `aif intent`
│   ├── style.py              # ruff stage and `aif fix`
│   ├── types.py              # mypy stage (structured type errors)
│   ├── dynamic.py            # AIF010 references and AIF013 dynamic dispatch
│   ├── model.py              # project model: classes, imports, type resolution
│   ├── members.py            # AIF012 member checks (classes and instances)
│   ├── thirdparty.py         # AIF014/AIF015 third-party and stdlib import validation
│   ├── fuzz.py               # contract fuzzing (CON001-CON005)
│   ├── scaffold.py           # `aif init`
│   ├── templates/            # files copied by `aif init` (hooks mirror scripts/)
│   ├── bounds.py             # integer ranges inferred from `requires`, used by fuzz
│   ├── effects.py            # rules AIF008-AIF011
│   └── patch.py              # `aif patch`: replace one function/class with rollback
├── domain/                   # pure logic
│   └── transfer.py           # example: transfer(), persist()
├── ports/                    # effect interfaces
│   └── db.py                 # example: DbWrite protocol
├── adapters/                 # real port implementations
│   └── sqlite_db.py          # example: SqliteDb implements DbWrite
├── tests/
│   ├── test_transfer.py      # property test with Hypothesis
│   ├── framework/            # tests of the framework itself
│   └── test_sqlite_db.py     # adapter roundtrip + end-to-end domain -> port -> adapter
├── scripts/
│   ├── commit-msg            # git hook: Intent trailer + Scope check
│   ├── pre-commit            # git hook: aif check
│   └── install-hooks.sh      # copies the hooks into .git/hooks
└── docs/                     # this documentation
```

## Module responsibilities

| Module | Public API | Role |
|---|---|---|
| `aif.contract` | `contract`, `ContractViolation` | Runtime contract checking; disabled with `AIF_CONTRACTS=off` |
| `aif.index` | `generate`, `save`, `source_files`, `module_of` | Builds the symbol map from the AST |
| `aif.lint` | `run` | Per-file rules, then delegates to `effects.run` |
| `aif.model` | `Model` | Project-wide class/function model with import and type resolution |
| `aif.members` | `check_module` | AIF012 for classes and inferred instances |
| `aif.dynamic` | `banned_references`, `dynamic_calls` | AIF010 references and AIF013 |
| `aif.thirdparty` | `Resolver`, `check` | Locates packages without importing and reads their namespaces |
| `aif.fuzz` | `run` | Property-checks every `@contract(ensures=...)` from type hints |
| `aif.scaffold` | `init` | Creates a new AIF project from `aif/templates/` |
| `aif.bounds` | `infer` | Reads simple numeric comparisons from a `requires` lambda |
| `aif.effects` | `run` | Capability/effect matching, direct I/O calls, import graph |
| `aif.config` | `Config`, `load` | Reads `[aif]` from `aif.toml` |
| `aif.agents` | `render`, `stale`, `write` | Generates agent instruction files from `.aif/protocol.md` |
| `aif.intents` | `run`, `create`, `listing`, `check_message` | Validates intents and commit trailers |
| `aif.style` | `run`, `fix` | Canonical formatting and style rules via ruff |
| `aif.types` | `run` | Runs mypy and converts output to AIF errors |
| `aif.patch` | `apply` | Function-level edit with diff, lint gate and rollback |
| `aif.cli` | `check`, `main` | Orchestrates index -> style -> intents -> lint -> types -> tests; `fix`; dispatches `patch` |

## Index format (`.aif/index.json`)

```json
{
  "domain.transfer": {
    "transfer": {
      "kind": "function",
      "args": ["source: Account", "target: Account", "amount: Decimal"],
      "returns": "TransferResult",
      "contract": {"requires": "...", "ensures": "...", "effects": "[]"},
      "doc": "Move `amount` from source to target ...",
      "line": 27
    },
    "Account": {"kind": "class", "line": 9, "doc": "", "bases": [], "methods": {}, "attributes": ["id", "balance"], "instance_attributes": []}
  }
}
```

Top-level functions and classes are indexed. Each class lists its `methods` (`kind: "method"`, `self`/`cls` omitted from `args`) and its `attributes` (annotated fields, assignments, nested classes), `instance_attributes` (`self.x = ...`) and `bases`. The file is regenerated on every `aif check`; never edit it by hand.

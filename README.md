# AIF: AI-First Framework (Python)

Conventions and tooling that give AI coding agents what a purpose-built language would: **one canonical form, contracts, explicit effects, and structured feedback**, while keeping plain Python.

An agent works in a loop: change code, run `aif check --json`, read the structured errors (`rule`, `file`, `line`, `cause`, `suggestion`, `counterexample`), fix, repeat.

## What `aif check` verifies

| Stage | Tool | Catches |
|---|---|---|
| Style | ruff | formatting and lint drift (one canonical form) |
| Agent files | built-in | `AGENTS.md`, `CLAUDE.md`, Cursor rules out of sync with `.aif/protocol.md` |
| Intents | built-in | missing or malformed `.aif/intents/*.md`, files outside the intent scope |
| Lint and effects | built-in (AST) | invented names/imports/members, I/O in pure code, effects not declared by signature, dynamic dispatch |
| Types | mypy `--strict` | type errors in code and tests; adapters not matching their port |
| Contract fuzzing | Hypothesis | `@contract(ensures=...)` violated by generated inputs, with a counterexample |
| Tests | pytest | contract violations as structured counterexamples |

Each stage runs only if the previous one passed, so feedback is always about one kind of problem.

## Architecture in one picture

```
domain/    pure logic. No I/O, @contract required.
ports/     Protocols for every effect (DbWrite, Clock, ...).
adapters/  implementations of ports (SQLite, HTTP, ...).
```

Effects are declared in the function signature through capability types (`db: DbWrite`) and mirrored in `@contract(effects=[...])`; the checker rejects any mismatch.

```python
@contract(
    requires=lambda source, amount: amount > 0 and source.balance >= amount,
    ensures=lambda r, source, target: r.source.balance + r.target.balance == source.balance + target.balance,
    effects=[],
)
def transfer(source: Account, target: Account, amount: Decimal) -> TransferResult: ...
```

## Quick start

Requires Python 3.11+ and git. AIF is not on PyPI yet, so install it from GitHub:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "git+https://github.com/robmlopes/ai-first-framework.git"

aif init my-app                    # new project that already passes `aif check`
cd my-app
pip install -e ".[dev]"            # pytest, hypothesis, mypy, ruff
aif check --json                   # expected: {"ok": true, "errors": []}

git add -A && git commit -m "chore: bootstrap

Intent: bootstrap"                 # hooks require the Intent trailer
aif intent new my-feature "What and why"
```

The full walkthrough (first feature, effects and ports, using an AI agent, troubleshooting) is in [docs/getting-started.md](docs/getting-started.md).

### Working on the framework itself

```bash
git clone https://github.com/robmlopes/ai-first-framework.git && cd ai-first-framework
pip install -e ".[dev]"
sh scripts/install-hooks.sh        # git hooks: pre-commit + commit-msg
aif check --json                   # verifies the example (money transfer, SQLite adapter) and the framework itself
```

## Commands

| Command | Purpose |
|---|---|
| `aif check [--json]` | run the whole pipeline |
| `aif fuzz` | run only contract fuzzing |
| `aif index` | write `.aif/index.json` (symbols, signatures, contracts, members) |
| `aif patch FILE SYMBOL[.method]` | replace one function, class or method, with lint rollback |
| `aif fix` | apply ruff formatting and safe fixes |
| `aif intent new\|list\|commit-msg` | manage intents; the commit hook enforces `Intent: <id>` and scope |
| `aif agents` | regenerate agent instruction files from `.aif/protocol.md` |
| `aif init [DIR]` | scaffold a new project |

## Documentation

Full documentation is in [docs/](docs/README.md): architecture, project structure, contracts, every lint rule (AIF001-AIF015, CON001-CON005, INT001-INT006, AGT001), CLI, configuration, agent protocol, workflow and known limitations.

## License

[The Unlicense](LICENSE): public domain, use it for anything without conditions.

## Honest limits

AIF raises the cost of mistakes; it does not prove correctness. Contracts are sampled, not proved; analysis skips what it cannot infer rather than guessing. See [docs/limitations.md](docs/limitations.md).

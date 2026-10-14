# Getting started: your first AIF project

This guide takes you from nothing to a verified project with its first feature. It assumes Python 3.11 or newer and git.

## 1. Install the framework

AIF is not on PyPI yet; install it from GitHub, preferably in a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install "git+https://github.com/robmlopes/ai-first-framework.git"
aif --help
```

To pin a version, append a tag or commit: `...ai-first-framework.git@<tag-or-sha>`.

## 2. Create the project

```bash
aif init my-app
cd my-app
pip install -e ".[dev]"              # pytest, hypothesis, mypy, ruff
aif check --json                     # expected: {"ok": true, "errors": []}
```

`aif init` creates:

| Path | Purpose |
|---|---|
| `domain/` | pure business logic: no I/O, `@contract` required |
| `ports/` | `Protocol` interfaces for every effect (database, clock, HTTP) |
| `adapters/` | implementations of the ports |
| `tests/` | your tests; `tests/strategies.py` registers domain input types for the fuzzer |
| `aif.toml` | framework configuration (see [configuration.md](configuration.md)) |
| `.aif/protocol.md` | the rules your AI agent follows; the single source of truth |
| `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/aif.mdc` | generated from the protocol; do not edit by hand |
| `.aif/intents/bootstrap.md` | the first intent |
| `scripts/` + `.git/hooks/` | `pre-commit` and `commit-msg` hooks (installed automatically unless `--no-git`) |

Options: `aif init DIR --no-git` skips `git init` and the hooks; `--profile web-api` (FastAPI) or `--profile cli` also creates an entry layer with a composition root and a starter test. The command never overwrites existing files and refuses a directory that already has an `aif.toml`.

## 3. Make the first commit

The hooks require an `Intent:` trailer on every commit. Commit the skeleton **before** adding code, so the bootstrap intent only covers the skeleton.

```bash
git add -A
git commit -m "chore: bootstrap

Intent: bootstrap"
```

## 4. Add a feature

Every change belongs to an intent: a short Markdown file that says why the change exists and which files it may touch.

```bash
aif intent new discount "Apply a discount to a price"
```

Edit `.aif/intents/discount.md`:

```markdown
# Apply a discount to a price

## Why
Shops lower a price by a percentage and must never produce a negative price.

## Scope
- domain/pricing.py

## Acceptance
- The discounted price is never negative and never above the original.
```

Then work in this order: **contract, test, implementation**.

```python
# domain/pricing.py
from aif import contract


@contract(
    requires=lambda price, percent: price >= 0 and 0 <= percent <= 100,
    ensures=lambda r, price: 0 <= r <= price,
)
def discounted(price: int, percent: int) -> int:
    """Price in cents after a percentage discount (rounded down)."""
    return price * (100 - percent) // 100
```

```python
# tests/test_pricing.py
from domain.pricing import discounted


def test_half_price() -> None:
    assert discounted(1000, 50) == 500
```

Run the verification and fix whatever it reports (`aif fix` handles formatting and import order):

```bash
aif check --json
```

Commit with the intent in the message:

```bash
git add -A
git commit -m "feat: discounted price

Intent: discount"
```

## 5. Fast feedback while you work

```bash
aif check --changed --json     # style and lint only on changed files; fuzz is cached
aif check --background         # returns at once; for tools with a short timeout
aif status                     # result of the last check (exit 3 while running)
aif stats                      # attempts before ok, most frequent rules, time per stage
```

Run the plain `aif check --json` before you finish: the hooks do.

## 6. What `aif check` tells you

Stages run in order and stop at the first one that fails, so each report is about one kind of problem:

| Stage | Typical error | What to do |
|---|---|---|
| `style` | `F401`, `format` | `aif fix` |
| `agents` | `AGT001` | `aif agents` |
| `intents` | `INT006` file outside scope | add the file to the intent's `Scope`, or split the commit |
| `lint`, `effects` | `AIF010` `open()` or `datetime.now()` in `domain/` | move the I/O or the clock read behind a port in `ports/` |
| `lint` | `AIF005` function too long | extract the block named in the `suggestion`; code lines only are counted |
| `effects` | `AIF016` web code imports an adapter | take a port as a parameter; build the adapter in the composition root |
| `types` | mypy error | fix the type or the signature |
| `fuzz` | `CON001` with a `counterexample` | the contract failed for generated inputs: fix the code or the contract |
| `tests` | contract violated | same, with the exact failing inputs |

Every error has `rule`, `file`, `line`, `cause` and `suggestion`; see [lint-rules.md](lint-rules.md) for all rules.

## 7. Effects: database, files, network

Pure code cannot touch the outside world. Declare the need as a port, ask for it by type, and list it in the contract:

```python
# ports/db.py
from typing import Protocol


class DbWrite(Protocol):
    def save(self, key: str, value: str) -> None: ...
```

```toml
# aif.toml
[aif.capabilities]
DbWrite = ["db.write"]
```

```python
# domain/store.py
from aif import contract
from ports.db import DbWrite


@contract(effects=["db.write"])
def store(key: str, value: str, db: DbWrite) -> None:
    db.save(key, value)
```

List every file the intent touches in its `Scope` (here also `domain/store.py` and `ports/db.py`). The implementation (SQLite, Postgres, an in-memory fake for tests) lives in `adapters/`. See the worked example in [architecture.md](architecture.md).

## 8. Using an AI agent

Point your agent at the repository. It reads `AGENTS.md` (or `CLAUDE.md`, or the Cursor rule), which tells it to consult `.aif/index.json`, work contract first, run `aif check --json`, and stop after five failed attempts. The details are in [agent-protocol.md](agent-protocol.md). To change the rules, edit `.aif/protocol.md` and run `aif agents`.

## 9. Third-party packages

A package must be listed in `pyproject.toml` **and** in `third_party` in `aif.toml`, otherwise `aif check` reports `AIF014`:

```toml
[aif]
third_party = ["httpx"]
```

## 10. Cloning an existing AIF project

Git does not version `.git/hooks`, so install them after cloning:

```bash
git clone <url> && cd <project>
pip install "git+https://github.com/robmlopes/ai-first-framework.git"
pip install -e ".[dev]"
sh scripts/install-hooks.sh
aif check --json
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `mypy did not run` | mypy not installed in the active environment | `pip install -e ".[dev]"` |
| `Untyped decorator` / `import-untyped` for `aif` | an old install without `py.typed` | reinstall the framework from GitHub |
| `CON004` on a contract | `requires` rejects almost every generated input | use simple numeric bounds, or pass `strategies=` to `@contract` |
| `CON003` | a parameter has no type hint | annotate it, or pass `strategies=` |
| `AIF014` for a package you installed | not declared in `third_party` | add it to `aif.toml` |
| hook rejects the commit with `INT004` | no `Intent: <id>` trailer | add it as the last line of the message |
| hook rejects the commit with `INT006` | a staged file is not in the cited intent's `Scope` | add the file to that intent, or commit it under another intent |
| hook says `No module named aif` | the hook found a Python without the framework | activate the virtual environment where you installed `aif`, then commit again |
| `aif check` is slow | fuzzing runs 100 examples per contract | lower `fuzz_examples` or set `fuzz = false` while iterating, or use `aif fuzz` alone |

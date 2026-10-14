# AIF framework tooling

## Why
The framework itself (CLI, lint rules, hooks, CI, packaging) evolves under its own intent so every commit stays traceable.

## Scope
- .aif/protocol.md
- .cursor/rules/aif.mdc
- .github/workflows/aif.yml
- .gitignore
- AGENTS.md
- CLAUDE.md
- aif.toml
- aif/__init__.py
- aif/__main__.py
- aif/agents.py
- aif/cli.py
- aif/config.py
- aif/contract.py
- aif/effects.py
- aif/index.py
- aif/intents.py
- aif/lint.py
- aif/patch.py
- aif/style.py
- aif/types.py
- pyproject.toml
- scripts/commit-msg
- scripts/install-hooks.sh
- scripts/pre-commit

## Acceptance
- `aif check --json` returns ok.
- Framework tests in tests/framework pass.

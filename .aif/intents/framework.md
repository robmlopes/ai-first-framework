# AIF framework tooling

## Why
The framework itself (CLI, lint rules, hooks, CI, packaging) evolves under its own intent so every commit stays traceable.

## Scope
- .aif/protocol.md
- .cursor/rules/aif.mdc
- .github/workflows/aif.yml
- .gitignore
- AGENTS.md
- CHANGELOG.md
- CLAUDE.md
- LICENSE
- README.md
- aif.toml
- aif/__init__.py
- aif/__main__.py
- aif/agents.py
- aif/bounds.py
- aif/cache.py
- aif/cli.py
- aif/config.py
- aif/contract.py
- aif/docscheck.py
- aif/dynamic.py
- aif/effects.py
- aif/env.py
- aif/fuzz.py
- aif/fuzzreport.py
- aif/history.py
- aif/index.py
- aif/intents.py
- aif/limits.py
- aif/lint.py
- aif/members.py
- aif/model.py
- aif/patch.py
- aif/pipeline.py
- aif/py.typed
- aif/scaffold.py
- aif/style.py
- aif/templates/aif.toml
- aif/templates/bootstrap-intent.md
- aif/templates/clock.py.txt
- aif/templates/commit-msg
- aif/templates/gitignore
- aif/templates/pre-commit
- aif/templates/profiles/cli-main.py.txt
- aif/templates/profiles/cli-test.py.txt
- aif/templates/profiles/cli.toml
- aif/templates/profiles/web-api-main.py.txt
- aif/templates/profiles/web-api-test.py.txt
- aif/templates/profiles/web-api.toml
- aif/templates/protocol.md
- aif/templates/pyproject.toml
- aif/templates/strategies.py.txt
- aif/thirdparty.py
- aif/types.py
- aif/upgrade.py
- pyproject.toml
- scripts/commit-msg
- scripts/install-hooks.sh
- scripts/pre-commit

## Acceptance
- `aif check --json` returns ok.
- Framework tests in tests/framework pass.

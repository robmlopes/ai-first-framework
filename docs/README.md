# AIF documentation

AIF (AI-First Framework) is a set of conventions and tools that keeps an existing language (Python here) but gives AI agents what a purpose-built language would: a canonical form, contracts, explicit effects and structured feedback.

| Document | Content |
|---|---|
| [architecture.md](architecture.md) | Principles, layers (domain / ports / adapters), dependency rules |
| [project-structure.md](project-structure.md) | Directory tree and what each file does |
| [contracts.md](contracts.md) | The `@contract` decorator, effects and capabilities |
| [lint-rules.md](lint-rules.md) | Every AIF rule (AIF001-AIF015) with examples |
| [cli.md](cli.md) | `aif check`, `aif index`, JSON output schema |
| [configuration.md](configuration.md) | `aif.toml` reference |
| [agent-protocol.md](agent-protocol.md) | The loop an AI agent must follow |
| [conventions.md](conventions.md) | Language and naming standards (English everywhere) |
| [workflow.md](workflow.md) | Git hooks, CI, framework tests, intent scope |
| [limitations.md](limitations.md) | Known limits and roadmap |

## Quick start

```bash
pip install -e ".[dev]"           # Python 3.11+; installs the `aif` command
aif init my-project                # or start a new project that already passes `aif check`
aif index                          # writes .aif/index.json
aif check --json                   # full verification, structured output
sh scripts/install-hooks.sh        # git hooks: pre-commit + commit-msg
```

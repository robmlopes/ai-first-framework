# Changelog

Versions below 1.0.0 may change rules, `aif.toml` keys and JSON formats without notice.

## 0.1.0

First tagged version.

- Canonical form: ruff, mypy `--strict`, structured JSON errors (`rule`, `file`, `line`, `cause`, `suggestion`).
- Lint rules AIF001-AIF016 with layering (`domain` / `ports` / `adapters`, optional entry layers).
- Effects declared in `@contract` and checked statically; contracts fuzzed with Hypothesis (CON001-CON005).
- Intents with commit scope (INT001-INT006), git hooks, `aif patch`, symbol index, agent files (AGT001).
- Per-layer limits on code lines with warnings at 90% and extraction hints.
- Faster feedback: `--changed`, fuzz cache, parallel stages, `--background` with `aif status`, timings.
- Clock rule: date/time types allowed, clock reads banned; `Clock` port in the template.
- Run history and `aif stats`; `aif fuzz --report`; `aif docs` (opt-in `docs_check`).
- `aif init` with `--profile web-api` and `--profile cli`.
- CI on Python 3.11, 3.12 and 3.13.

Known limits: Python only; fuzzing does not test concurrency; not yet measured with a real agent.

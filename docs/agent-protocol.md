# Agent protocol

Source of truth: `.aif/protocol.md`. `aif agents` generates `AGENTS.md`, `CLAUDE.md` and `.cursor/rules/aif.mdc` from it; `aif check` flags drift (AGT001). Do not edit the generated files.

1. Read `.aif/index.json` (`python -m aif index`) and the intent file for the task (`python -m aif intent list`; create one with `aif intent new ID TITLE`). Never invent names.
2. Plan which modules change (ideally one or two).
3. Prefer `aif patch FILE SYMBOL` (or `Class.method`) over rewriting whole files. Write the contract and tests first, then the implementation.
4. Run `python -m aif check --json`.
5. Fix from the diagnostics: use `counterexample` and `suggestion`. Maximum 5 attempts, then stop and report the blocker.
6. Commit one atomic change with an `Intent: <id>` trailer in the message (enforced by `scripts/commit-msg`, which also rejects staged files outside the intent's `Scope`).

## Placement guide

| You need to... | Put it in |
|---|---|
| Add business logic | `domain/` with `@contract` |
| Talk to the outside world | Protocol in `ports/`, implementation in `adapters/`, register capability in `aif.toml` |
| Verify behaviour | `tests/` with Hypothesis properties derived from `ensures` |

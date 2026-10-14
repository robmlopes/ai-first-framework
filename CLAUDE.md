# Agent protocol (AIF)

1. Read `.aif/index.json` (run `python -m aif index`) and consult it before importing or calling any project symbol. Never invent names.
2. Business logic goes in `domain/` (pure, no I/O, `@contract` required). Effects enter as Protocols in `ports/`; implementations live in `adapters/`.
3. Every task has an intent in `.aif/intents/` (`python -m aif intent list` / `new ID TITLE`). End commit messages with `Intent: <id>`.
4. Work order: contract -> test (Hypothesis) -> implementation.
5. Run `python -m aif check --json` (ruff -> intents -> lint -> mypy --strict -> tests) and fix using `errors[].counterexample` and `suggestion`. If only style errors remain, run `python -m aif fix`.
6. At most 5 attempts per task; then stop and report what blocked you.
7. Small changes: at most 1-2 modules per task.
8. All code, comments, docs and identifiers are written in English.
9. Edit existing code with `python -m aif patch FILE SYMBOL` (one function, class or `Class.method` at a time) instead of rewriting files.

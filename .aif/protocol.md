1. Read `.aif/index.json` (run `aif index`) and consult it before importing or calling any project symbol. Never invent names.
2. Business logic goes in `domain/` (pure, no I/O, `@contract` required). Effects enter as Protocols in `ports/`; implementations live in `adapters/`.
3. Every task has an intent in `.aif/intents/` (`aif intent list` / `aif intent new ID TITLE`). End commit messages with `Intent: <id>`; staged files must be inside that intent's `Scope`.
4. Work order: contract -> test (Hypothesis) -> implementation.
5. Run `aif check --json` (ruff -> intents -> lint/effects -> mypy --strict -> contract fuzzing -> tests) and fix using `errors[].counterexample` and `suggestion`. A `fuzz` error means a contract failed for generated inputs: fix the code or the contract, never the generated input. If only style errors remain, run `aif fix`.
   While iterating use `aif check --changed --json` (style and lint only on changed files); run the full `aif check --json` before you finish. If a command may exceed your tool timeout, run `aif check --background` and poll `aif status`. `warnings` in the output (AIF005 at 90% of a limit) are not failures: split before they become errors.
6. At most 5 attempts per task; then stop and report what blocked you.
7. Small changes: at most 1-2 modules per task.
8. All code, comments, docs and identifiers are written in English.
9. Edit existing code with `aif patch FILE SYMBOL` (one function, class or `Class.method` at a time) instead of rewriting files.
10. Do not bypass the hooks (`--no-verify`) or edit `.aif/index.json` by hand.

`python -m aif ...` is equivalent to `aif ...` when the package is not installed.

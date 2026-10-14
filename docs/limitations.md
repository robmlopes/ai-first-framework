# Limitations and roadmap

## Known limits

- **Discipline, not guarantee.** Python cannot prevent bypassing the conventions; strength comes from lint and CI.
- **Runtime contracts prove nothing** beyond the cases exercised; Hypothesis helps but is not proof.
- **Specification cost.** A wrong contract yields "correct" code doing the wrong thing.
- **Overhead on tiny projects.**
- **Index freshness.** Regenerated on every `aif check`; stale if only `aif index` is skipped elsewhere.
- Capability matching resolves import/module aliases and simple assignments, but not aliases created dynamically or inside functions.
- AIF010/AIF013 are static: they catch references and dynamic dispatch patterns in pure modules, but cannot follow a callable stored in an object field or passed through several layers of arguments.
- AIF012 infers types only where they are certain (see `lint-rules.md`); everything else is skipped, so it can miss errors but should not raise false ones.
- Imports are validated for project modules only; third-party imports are not checked against any index.
- AIF011 follows module-level import paths that start in the domain.
- `aif patch` handles top-level definitions and methods of top-level classes. It cannot patch nested functions, module-level statements or imports, and does not run tests.
- Type checking covers `source_dirs` and `tests/` (`typecheck_tests`). Port conformance needs an explicit typed assignment such as `as_db_write`.

## Roadmap

Open: TypeScript port of the framework (separate project); pyright support.

1. ~~`aif patch`~~ (done, including methods).
2. ~~SQLite adapter example~~ (done: `adapters/sqlite_db.py`).
3. ~~`.aif/intents/` support~~ (done, including the Scope check at commit time, INT006).
4. ~~Ruff and mypy stages~~ (done; pyright not supported).
5. ~~Git hooks, CI, framework tests, `aif` entry point, agent files~~ (done).
6. ~~Method-level indexing~~ (done). `Class.member` references are validated (AIF012). Relative imports and `import x.y` are validated (AIF006).

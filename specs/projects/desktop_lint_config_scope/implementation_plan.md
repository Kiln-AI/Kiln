---
status: complete
---

# Implementation Plan: Desktop Lint Config Scope

Fix first, flip last. The config change goes in the final phase so CI is green at every commit
and no phase ever carries a suppression to make the build pass.

Phases 1–3 are verified with the audit command from the functional spec, since plain
`uv run ruff check` cannot see these findings until Phase 4.

## Phases

- [ ] **Phase 1: `RUF059` sweep** — ~74 unused unpacked variables across 17 test files, nearly all
      under `git_sync/`. One repetitive shape. Underscore-prefix each, but read every site for a
      missing assertion first. No bulk auto-fix.

- [ ] **Phase 2: `I001` import sorting** — ~51 findings across 50 files, produced entirely by
      `--select I --fix` plus `ruff format`. Isolated so a wide, purely mechanical diff does not
      hide anything in review.

- [ ] **Phase 3: The judgment tail** — the remaining ~22 findings, ~9 files. `FAST002` `Annotated`
      conversions in `git_sync_api.py` (run `check_schema.sh` here), `ClassVar` on the
      `registry.py` singleton, the `noop.py` relative import, and the `RUF010`/`RUF022`/`RUF005`/
      `RUF015` one-offs.

- [ ] **Phase 4: Flip the config** — move the generated-client exclude to root `pyproject.toml`,
      delete `[tool.ruff]` from `app/desktop/pyproject.toml`. Re-run the full check to catch
      anything that landed mid-project, confirm the generated client is still excluded and
      unmodified, then `uv run ./checks.sh --agent-mode`.

Phases 1–3 are independent and can land in any order, or together, if that reads better in review.
Phase 4 must be last.

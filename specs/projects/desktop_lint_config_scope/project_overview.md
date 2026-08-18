---
status: draft
---

# Desktop Lint Config Scope — Project Overview

`app/desktop/` has been silently exempt from most of the repo's ruff rules. Restore
enforcement, and deal with the backlog that restoring it surfaces.

## Why

Ruff does not merge configuration up the directory tree. It walks up from each file,
and the **first** `pyproject.toml` containing a `[tool.ruff]` section becomes the config
root for that subtree — ancestors are ignored entirely.

The root `pyproject.toml` sets:

```toml
[tool.ruff.lint]
extend-select = ["I","F401","RUF","FAST","TID"]
```

But `app/desktop/pyproject.toml` declares its own section, containing only an exclude for
generated client code:

```toml
[tool.ruff]
exclude = ["studio_server/api_client/kiln_ai_server_client"]
```

That is sufficient to make it the config root, so the root's `extend-select` never reaches
anything under `app/desktop/`. This looks unintended: the exclude was written to skip
generated code, not to opt the desktop app out of the project's lint rules.

Confirmed empirically — an identical probe file dropped into both trees reports 2 errors
under `app/desktop` and 4 under `libs/core`.

### What is actually lost

| Rule | Covers | Enforced in `app/desktop`? |
|---|---|---|
| `F401` | Unused imports | **Yes** — part of ruff's default `F` set, so listing it in `extend-select` is redundant |
| `I` | Import sorting | No |
| `RUF` | Ruff rules, incl. `RUF012` mutable class defaults | No |
| `FAST` | FastAPI-specific linting | No |
| `TID` | Banned APIs, incl. `typing.cast` | No |

`FAST` is the pointed one: `app/desktop` is the tree that is almost entirely FastAPI, so the
FastAPI ruleset is off precisely where it was meant to apply.

`app/desktop/pyproject.toml` is the **only** project subtree with this problem — every other
Python directory inherits the root config correctly.

## Scale of the backlog

Running the root ruleset over `app/desktop` today:

```
 74  RUF059   unused-unpacked-variable
 43  I001     unsorted-imports                    [auto-fixable]
  9  FAST002  fast-api-non-annotated-dependency
  5  RUF010   explicit-f-string-type-conversion   [auto-fixable]
  4  RUF012   mutable-class-default
  3  TID252   relative-imports
  2  RUF100   unused-noqa                         [auto-fixable]
  1  RUF005   collection-literal-concatenation
  1  RUF015   unnecessary-iterable-allocation-for-first-element
  1  RUF022   unsorted-dunder-all                 [auto-fixable]
```

**143 findings across 69 files.** 51 are auto-fixable; a further 88 have fixes available only
under `--unsafe-fixes`.

The config change itself is three lines. The backlog is the actual project.

## Goal

`app/desktop` linted under the same rules as the rest of the repo, with CI enforcing it and
no rules suppressed to get there.

## Decisions to make

1. **How to land the backlog.** One large mechanical PR, or the config change plus a phased
   cleanup? 74 of the 143 are `RUF059` (unused unpacked variables), which is a single
   repetitive shape and may be worth its own pass.
2. **Auto-fix policy.** `--fix` covers 51. The other 88 need `--unsafe-fixes`, which by
   definition can change behavior — these likely want to be done by hand or reviewed
   individually rather than applied in bulk.
3. **`RUF012` deserves real attention, not a mechanical fix.** Mutable class defaults are a
   genuine bug class, and the root config's own comment calls them out as important. Each of
   the 4 should be read for whether it is an actual latent bug rather than annotated with
   `ClassVar` to silence it.
4. **Whether any rule genuinely should be off for this tree.** If so, disable it explicitly
   and deliberately in the root config with a comment — the current state is an accident, and
   the outcome should not be another silent exemption.
5. **Preserving the original intent.** The generated-client exclude must keep working. Moving
   it to the root config's `exclude` is the obvious approach; confirm the path resolves
   correctly from the root.

## Out of scope

- Any behavioral change to the desktop app. This is lint conformance only.
- The web UI's eslint/prettier configuration — unexamined here, and unrelated.
- Other quality tooling (`ty`, pytest config) — the same config-root question could apply, but
  it has not been checked and should not be assumed.

## Notes

Found while reviewing PR #1648 (code-judge LLM calls): a reviewer caught an import-ordering
slip in `app/desktop/studio_server/code_tool_api.py` that CI had not flagged. Running the root
ruleset over just the five desktop files that PR touched surfaced 3 pre-existing `I001` blocks
and 2 `RUF012` findings, none introduced by that work.

That PR deliberately did not touch any lint configuration, and left the pre-existing findings
alone. Nothing about this project is a revert of it.

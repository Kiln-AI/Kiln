---
status: complete
---

# Phase 6: Pre-merge removal of the Jev model entry

## Overview

The Jev model entry was added in Phase 3 so the provider could be exercised end to end on
the branch, carrying a `TODO` saying it must come out before merge. It has to come out
because an older client reading the remote model config would show the model labelled with
a raw provider ID and offer a provider it cannot connect to. Phase 7, a separate PR after
the client release that carries the provider, re-adds it.

This phase removes the entry, its two enum members, and the `TODO`; confirms no `TODO`
comment introduced by this project survives anywhere in the diff against `main`; and leaves
the full `checks.sh` green.

Nothing else in the feature is removed: `ModelProviderName.typesafe`, `ModelAdapterId.jev`,
`KilnModelProvider.adapter`, `JevAdapter`, `JevClient`, the eval wiring and the web UI all
stay. With the entry gone, Jev is reachable only through the user/custom model registry
until Phase 7.

## Steps

1. `libs/core/kiln_ai/adapters/ml_model_list.py`: delete the `KilnModel` entry for Jev 1.13
   at the end of `built_in_models`, together with the `# Jev 1.13` header comment and the
   three-line `# TODO: remove before merge; ...` comment above it.
2. Same file: delete `ModelFamily.jev` and `ModelName.jev_1_13`. Keep `ModelAdapterId.jev`
   and the `adapter` field docstring — both are provider plumbing, not model-list content.
3. Verify by grep that no code references the two removed members. The three tests that
   name the model (`test_adapter_registry.py`, `test_jev_adapter.py`, `test_jev_judge.py`)
   use the raw string `"jev_1_13"` as a registry model name, not the enum, and mock the
   provider lookup, so they must keep passing untouched. If any test fails only because the
   entry is gone, report it rather than patching the test.
4. Sweep the whole diff against `origin/main` (`84a698a...HEAD`) for `TODO`/`FIXME` in added
   lines, matching the CI check in `.github/workflows/debug_detector.yml` (which excludes
   `*.md`, so spec prose describing the `TODO` is out of scope). Confirm nothing remains.
5. Spell-check this project's added prose as far as the sandbox allows (`misspell` is not
   installed); report what was and was not checkable.
6. Run `uv run ./checks.sh --agent-mode` and leave it green.

## Tests

No new tests. The removal is covered by existing ones:

- `test_built_in_models_adapter_matches_provider` — keeps guarding that any future
  `typesafe` entry declares `adapter=jev`; with no entry it passes over the remaining
  models without a typesafe case.
- `test_jev_entry_routes_to_jev_adapter`, `test_jev_adapter.py`, `test_jev_judge.py` — all
  mock provider resolution, so they exercise the adapter and judge without the entry.
- The full Python and web suites in `checks.sh` confirm nothing else depended on the
  removed enum members.

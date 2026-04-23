---
status: complete
---

# Phase 10: Move `guides/` to `.config/legacy_guides/`

## Overview

Move the `guides/` directory out of the repo root into `.config/legacy_guides/`, delete the unused `kiln_preview.avif` (3.5 MB), and update all internal references. This continues the root cleanup effort.

## Steps

1. `git mv guides .config/legacy_guides` -- move the entire directory.
2. `git rm .config/legacy_guides/kiln_preview.avif` -- delete unused 3.5 MB file.
3. Update `README.md:69` -- change `src="guides/kiln_preview.gif"` to `src=".config/legacy_guides/kiln_preview.gif"` (relative path for now; user may want to revisit with a GitHub user-attachments URL).
4. Update `.config/legacy_guides/Fine Tuning LLM Models Guide.md:54` -- change the absolute GitHub URL from `.../main/guides/Synthetic%20Data%20Generation.md` to `.../main/.config/legacy_guides/Synthetic%20Data%20Generation.md`.
5. Grep for any remaining `guides/` references that need updating and fix them.
6. Run `uv run ./checks.sh --agent-mode` to verify nothing broke.

## Tests

- NA -- this is a file move and reference update only; no code logic changed.

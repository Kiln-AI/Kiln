---
status: complete
---

# Phase 16: Dependencies cleanup — remove redundant codemirror umbrella

## Overview

Remove the `codemirror` umbrella package from `app/web_ui/package.json`. The editor uses only the 5 granular `@codemirror/*` packages (commands, lang-python, language, state, view); the umbrella re-exports these plus unused transitive deps (~autocomplete, lint, search, crelt). Removing it shrinks the dependency tree without affecting the working editor.

## Steps

1. Confirm zero bare `codemirror` imports in `app/web_ui/src/` (grep).
2. Confirm the 5 granular `@codemirror/*` deps remain in `package.json`.
3. Remove the `"codemirror": "^6.0.2"` line from `app/web_ui/package.json` dependencies.
4. Run `npm install` from `app/web_ui` to re-resolve `package-lock.json`.
5. Verify `npm run build`, `npm run check`, and `npm run lint` all pass.

## Tests

- No new tests required — this is a dependency removal with no code changes. Build/check/lint serve as the verification.

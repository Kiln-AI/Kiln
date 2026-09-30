---
status: complete
---

# Phase 4: Trust Modal + Bugs

## Overview

Redesign the trust-code modal with new copy, a large warning icon (no yellow alert box), and dismiss-on-trust behavior so the Test Run pane shows "Running" on the page immediately after granting trust. Fix B1: reset `create_evaluator_loading` when `handle_submit` defers to the confirm-save or trust dialog, so the Save button does not get stuck spinning.

## Steps

1. **Trust modal markup** (`eval_config_builder.svelte`, lines 604-628)
   - Replace `alert alert-warning` yellow box with a large warning icon (reuse the SVG from `warning.svelte` at `w-10 h-10` size, `text-warning` color) positioned above the body text.
   - Update title to "Trust Code and Project?".
   - Body line 1: "This project wants to run Python code on your machine. Only proceed if you trust the eval code and this project."
   - Body line 2 (bold): "Never paste code from a stranger or the internet."
   - Buttons: Cancel + "Run -- I Trust This Code" (isWarning).

2. **Dismiss-on-trust flow** (`eval_config_builder.svelte`, `grant_trust_and_retry`)
   - Change `grant_trust_and_retry` so it does NOT await `run_test()` / `do_save()`. After granting trust, kick off the pending action without awaiting, then return `true` to close the dialog immediately.
   - This lets the Test Run pane show "Running" state on the page while the eval executes.

3. **Fix B1: reset loading on modal defer** (`eval_config_builder.svelte`, `handle_submit`)
   - In `handle_submit`, set `create_evaluator_loading = false` before showing the trust dialog or the confirm-save dialog, then return.
   - `do_save()` re-sets `create_evaluator_loading = true` when the user actually proceeds.
   - Also reset in the `run_test` trust path (already done at line 235, but verify).

4. **Tests** (`page.test.ts`)
   - B1 regression: after clicking Save on a code_eval with untrusted project, verify `create_evaluator_loading` resets (form-submit-button not disabled/spinning).
   - B1 regression: after clicking Save on non-trust type without valid test, verify loading resets when confirm dialog is shown.
   - Trust modal shows new title "Trust Code and Project?" (not old "Allow Code Execution").
   - Trust modal body contains new copy (no yellow alert text).
   - Trust modal icon: large warning icon present, no `alert-warning` class.
   - Dismiss-on-trust: after granting trust, the test run enters loading state on the page.

## Tests

- B1: `create_evaluator_loading` resets when deferring to trust dialog
- B1: `create_evaluator_loading` resets when deferring to confirm-save dialog
- Trust modal title is "Trust Code and Project?"
- Trust modal body contains new copy lines
- Trust modal has no yellow alert box (`alert-warning`)
- Trust modal has a large warning icon
- Dismiss-on-trust fires run without blocking the dialog

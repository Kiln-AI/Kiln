---
status: complete
---

# Phase 8: The eval's OpenEnv server on screen

## Overview

A grounded eval (one saved by an OpenEnv build) records `openenv_server_id`, but no screen shows
it. This phase adds a read-only "OpenEnv Server" row to the spec page's Properties and the eval
page's Evaluator Properties (`functional_spec.md`, "Follow-ups after v1", Phase 8). The value is
the server's name linked to its detail page; a deleted server shows its id, an archived one gets
"(Archived)". Changing the server is not offered.

## Steps

1. New `app/web_ui/src/lib/utils/openenv_server_property.ts`, shared by both pages:
   - `openenv_server_property(project_id: string, openenv_server_id: string, openenv_server:
     OpenEnvServer | null | undefined): UiProperty`. `undefined` means still loading
     ("Loading..."), `null` means it couldn't be loaded (the id), otherwise the name, with
     " (Archived)" when `is_archived`. Name "OpenEnv Server", link
     `openenv_server_detail_link(project_id, openenv_server_id)`.
   - `create_openenv_server_loader()`: a readable store of `OpenEnvServer | null | undefined`
     plus `load(project_id: string, openenv_server_id: string | null | undefined)`. Resets to
     `undefined`, calls `load_openenv_server`, sets the server or `null` on error, and ignores
     a response that a later `load` has superseded (the guard from
     `openenv_episode_properties.svelte`). A missing id makes no request.
2. Spec page (`specs/[project_id]/[task_id]/[spec_id]/+page.svelte`): create a loader, call
   `load(project_id, evaluator?.openenv_server_id)` reactively, and insert the row after
   "Test Dataset" only when `evaluator?.openenv_server_id` is set.
3. Eval page (`.../[spec_id]/[eval_id]/+page.svelte`): same loader; `get_eval_properties` takes
   the loaded server and pushes the row after "Golden Dataset" (the last dataset row) when
   `evaluator.openenv_server_id` is set, with a tooltip saying the eval's cases run in this
   server.

## Tests

- `openenv_server_property.test.ts`:
  - property shows the name and links the detail page
  - archived server gets " (Archived)"
  - `null` shows the id, still linked; `undefined` shows "Loading..."
  - loader sets the server after a load, `null` when the request fails
  - loader makes no request and stays `undefined` without an id
  - a stale response from an earlier load doesn't overwrite a later one
- `eval_detail.test.ts`:
  - an eval with `openenv_server_id` gets the "OpenEnv Server" row with the server's name and
    link, right after "Golden Dataset"
  - an eval without one has no such row

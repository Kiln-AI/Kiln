---
status: complete
---

# Phase 2: Git Re-Import Recovery (Backend)

## Overview

Adds the backend plumbing for the "remove conflicting project and re-import" recovery flow. This phase factors the existing `delete_project` logic into a shared helper so that both `delete_project` and the new `remove_conflicting_id` path on `save_config` use the same de-registration code.

## Steps

1. **Add `remove_project_from_config` to `libs/core/kiln_ai/utils/project_utils.py`**
   - New function that removes a project path from `Config.shared().projects` and from `Config.shared().git_sync_projects`.
   - Returns the `clone_path` if the project was git-synced, else `None`.
   - This is the persistent-config-only portion of project removal (no runtime registry teardown).

2. **Add `_deregister_project` helper to `app/desktop/git_sync/git_sync_api.py`**
   - Async wrapper that calls `remove_project_from_config` and then `GitSyncRegistry.unregister` if a `clone_path` was returned.
   - This is the full app-layer removal (config + runtime registry).

3. **Refactor `delete_project` endpoint to use `_deregister_project`**
   - Replace the inline config-removal logic with a call to `_deregister_project(str(project.path))`.
   - No change to external behavior or response shape.

4. **Add `remove_conflicting_id: bool = False` to `SaveConfigRequest`**
   - New optional field on the Pydantic model.

5. **Update `api_save_config` to handle `remove_conflicting_id=True`**
   - On `DuplicateProjectError` with the flag set: resolve the conflicting project via `project_from_id_core`, de-register it, then fall through to the normal save path.
   - With the flag `False` (default): behavior unchanged (raises 409).

## Tests

- `test_remove_project_from_config_removes_project_and_git_sync`: verifies both `projects` and `git_sync_projects` are updated, returns `clone_path`.
- `test_remove_project_from_config_non_git_synced`: verifies it works for non-git-synced projects, returns `None`.
- `test_remove_project_from_config_missing_project`: verifies idempotent behavior when the path isn't in config.
- `test_delete_project_uses_shared_helper`: verifies `delete_project` endpoint calls `_deregister_project` and still returns the expected response.
- `test_save_config_remove_conflicting_deregisters_and_saves`: verifies the full flow with `remove_conflicting_id=True`.
- `test_save_config_remove_conflicting_false_still_409`: verifies default behavior is unchanged.
- `test_save_config_remove_conflicting_no_conflict_is_noop`: verifies the flag is a no-op when there's no conflict.

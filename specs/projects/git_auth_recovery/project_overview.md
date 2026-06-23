---
status: complete
---

# Git Creds Error is Unrecoverable

A user had 1 project synced via Git, then hit an unrecoverable error state.

## Symptoms

- The `/tasks` API used by the task picker (the [list select](http://localhost:8757/setup/select_task) page, and the same control in the app) errored. The underlying cause was expired Git auth, but the API returned `{detail: "Cannot sync with remote. Check your connection."}`. The UX was bad: the picker showed `Tasks failed to load: [Object object]`.

## Fixes wanted

### 1. Fix the task-picker error display

Show the right error, not `[Object object]`. The API returns a reasonable string, but maybe not in the format the UI expects to render. Might change how the API returns the error, or how the UI renders it. Investigate and recommend.

### 2. Allow recovery when Git creds expire (or any other issue)

- **Option 1 (simple): allow importing again**, which goes through setup for fresh Git creds. This doesn't work today because re-import errors with "You already have a project with this ID. You must remove project X before adding this." If I have many projects that's reasonable (go to Settings > Manage projects > Remove). However, if I only have 1 project, we redirect to `/setup/select_task`, where it's not possible to remove — so I can't remove the old one to re-sync. Proposed solution: the import UI/API can show this error, then the button updates to "Remove existing and re-sync" (red), which calls back to the API with an extra flag like `remove_conflicting_id`.

- **Option 2: allow re-authenticating from the task picker** (seems big).

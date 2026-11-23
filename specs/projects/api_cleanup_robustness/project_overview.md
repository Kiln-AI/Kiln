---
status: draft
---

# API Cleanup and Robustness

A cleanup and robustness project: a batch of API fixes found while planning the Kiln MCP server and the harness-tuner port (`specs/projects/kiln_mcp_server` and `specs/projects/harness_tuner_port`, on branch `claude/ecstatic-wright-7glcz8`). The harness-tuner port depends on this work and will check that it was done, but does not own it.

The goal is to prevent accidental damage and accidental overfitting. It is not a defence against a caller that works to get around the rules.

## Items

1. **Few-shot and repair prompt generators copy eval items into prompts.** The `few_shot_`, `multi_shot_` and `repairs_` generators, and their chain-of-thought forms, pick up to 25 stored runs by rating, not by split (`libs/core/kiln_ai/adapters/prompt_builders.py`, around lines 204-234). A prompt built this way can contain items that an eval measures with. Change: skip every run that is in any split of any eval of the task: train, val and test. Train is included on purpose, because examples taken from the train split overfit the train score. This applies to every caller, always. Prompts that were already frozen into run configs are not changed.

2. **`save_sample` writes to any path.** `POST /api/projects/{project_id}/tasks/{task_id}/save_sample` (`app/desktop/studio_server/data_gen_api.py`, around lines 689-712) takes a whole `TaskRun` as its body. A `path` in the body made the server write the run file outside the project. An `id` equal to an existing run's id overwrote that run. Both were confirmed with real calls. Change: the server chooses the path and the id. Check whether other routes that take a whole Kiln datamodel object as a body have the same hole.

3. **Deleting a saved prompt or a code tool does not check for use.** `DELETE …/prompts/{prompt_id}` (`libs/server/kiln_server/prompt_api.py`, around lines 325-342) and `DELETE /api/projects/{project_id}/code_tools/{code_tool_id}` (`app/desktop/studio_server/code_tool_api.py`, around line 417) delete directly. A run config can reference a saved prompt by id and can list a code tool, so a delete can break a stored run config. Change: the delete fails with a clear error when the record is in use, and names what uses it.

4. **Prompts get archiving.** Add archiving to saved prompts, in the API and the UI, in the same way the other archivable records do it. Check first what exists today.

5. **Scan for other places where an immutable record can be deleted or edited.** Records that are meant to be immutable once created include run configs, saved prompts, skills, code tools and judge configs — anything a run config contains, really — plus select fields of tasks. Find every API route that edits or deletes such a record, and for each one either fix it or list it for the owner to decide. This scan was deliberately not done during planning, so do it here.

## Notes

- Each fix needs tests.
- Where a fix changes what the web UI can do, update the UI.

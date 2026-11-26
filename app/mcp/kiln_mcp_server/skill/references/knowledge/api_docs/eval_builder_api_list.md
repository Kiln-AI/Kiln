# Eval Builder API

Eval builder V2 review pipeline: judge and claim/evidence generation over alignment traces.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/multi_turn_pipeline`|POST|Run Multi-Turn Pipeline|Drive each multi-turn case against the task, then judge it, as one event stream.  The merged multi-t...|post_api_projects_project_id_tasks_task_id_eval_builder_multi_turn_pipeline.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/single_turn_pipeline`|POST|Run Single-Turn Review Pipeline|Run the task once on each generated input, then judge each run, as one stream.  The single-turn stre...|post_api_projects_project_id_tasks_task_id_eval_builder_single_turn_pipeline.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/judge_traces`|POST|Judge Saved Eval-Builder Results|Re-judge saved eval builder results with a new judge prompt, as an event stream.  [reload → judge] p...|post_api_projects_project_id_tasks_task_id_eval_builder_judge_traces.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/build_claims`|POST|Build Claims|Build the review claims for one judged trace, given its known verdict.  The multi-turn review's clai...|post_api_projects_project_id_tasks_task_id_eval_builder_build_claims.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/preflight_model`|POST|Preflight a Model Lane|Check that a model runs on the user's keys with one cheap completion.  The completion goes through t...|post_api_projects_project_id_tasks_task_id_eval_builder_preflight_model.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/author_judge`|POST|Author Judge|Author a spec-tailored judge prompt for the review — both arms.  Returns the PROMPT only — the judge...|post_api_projects_project_id_tasks_task_id_eval_builder_author_judge.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/refine_judge`|POST|Refine Judge|Propose a judge-prompt revision from the human's per-claim grades.  The refined prompt is a PROPOSAL...|post_api_projects_project_id_tasks_task_id_eval_builder_refine_judge.md|

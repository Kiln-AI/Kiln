# Eval Builder API

Eval builder V2 review pipeline: judge and claim/evidence generation over alignment traces.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/multi_turn_pipeline`|POST|Run Multi-Turn Pipeline|The merged multi-turn stream: [drive → judge] per case.  Emits (all frames `type`-discriminated; err...|post_api_projects_project_id_tasks_task_id_eval_builder_multi_turn_pipeline.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/single_turn_pipeline`|POST|Run Single-Turn Review Pipeline|The single-turn stream: [run → judge] per generated input.  The one-turn sibling of multi_turn_pipel...|post_api_projects_project_id_tasks_task_id_eval_builder_single_turn_pipeline.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/judge_traces`|POST|Judge Saved Eval-Builder Results|Re-judge previously driven results: [reload → judge] per case.  The judge calibration loop's re-scor...|post_api_projects_project_id_tasks_task_id_eval_builder_judge_traces.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/build_claims`|POST|Build Claims|Claims-only primitive: build claims for one trace given a known verdict.  The multi-turn review's cl...|post_api_projects_project_id_tasks_task_id_eval_builder_build_claims.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/preflight_model`|POST|Preflight a Model Lane|One cheap completion through the SAME adapter model/provider resolution a real run uses (that resolu...|post_api_projects_project_id_tasks_task_id_eval_builder_preflight_model.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/author_judge`|POST|Author Judge|Author a spec-tailored judge prompt for the review — both arms.  Returns the PROMPT only — the judge...|post_api_projects_project_id_tasks_task_id_eval_builder_author_judge.md|
|`/api/projects/{project_id}/tasks/{task_id}/eval_builder/refine_judge`|POST|Refine Judge|Propose a judge-prompt revision from the human's per-claim grades.  The refined prompt is a PROPOSAL...|post_api_projects_project_id_tasks_task_id_eval_builder_refine_judge.md|

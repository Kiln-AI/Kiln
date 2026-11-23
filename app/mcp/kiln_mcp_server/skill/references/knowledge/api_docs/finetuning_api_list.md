# Fine-tuning API

Create and manage fine-tuning jobs.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/dataset_splits`|GET|List Dataset Splits|List the task's dataset splits: frozen sets of runs used to fine-tune.|get_api_projects_project_id_tasks_task_id_dataset_splits.md|
|`/api/projects/{project_id}/tasks/{task_id}/dataset_splits`|POST|Create Dataset Split|Freeze a set of the task's runs into a dataset split for fine-tuning.|post_api_projects_project_id_tasks_task_id_dataset_splits.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes`|GET|List Finetunes|List the task's fine-tunes. With update_status, ask each provider for the job's current status first...|get_api_projects_project_id_tasks_task_id_finetunes.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes`|POST|Create Finetune|Start a fine-tune of the task on a dataset split. Starts a paid job at the provider.|post_api_projects_project_id_tasks_task_id_finetunes.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}`|GET|Get Finetune|Get one fine-tune with its job's current status from the provider.|get_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}`|PATCH|Update Finetune|Change a fine-tune's name or description.|patch_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md|
|`/api/finetune_providers`|GET|List Finetune Providers|List the providers that can fine-tune, with the base models each offers and whether it is enabled.|get_api_finetune_providers.md|
|`/api/finetune/hyperparameters/{provider_id}`|GET|List Finetune Hyperparameters|List the hyperparameters a fine-tune provider accepts, with their types.|get_api_finetune_hyperparameters_provider_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetune_dataset_info`|GET|Get Finetune Dataset Info|Get the task's dataset splits, fine-tunes and run counts by tag, for a fine-tune.  With tool_ids, on...|get_api_projects_project_id_tasks_task_id_finetune_dataset_info.md|
|`/api/download_dataset_jsonl`|GET|Download Dataset JSONL|Download one split of a dataset split as a JSONL file, in a fine-tuning format.|get_api_download_dataset_jsonl.md|

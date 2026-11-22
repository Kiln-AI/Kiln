# Fine-tuning API

Create and manage fine-tuning jobs.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/tasks/{task_id}/dataset_splits`|GET|List Dataset Splits||get_api_projects_project_id_tasks_task_id_dataset_splits.md|
|`/api/projects/{project_id}/tasks/{task_id}/dataset_splits`|POST|Create Dataset Split||post_api_projects_project_id_tasks_task_id_dataset_splits.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes`|GET|List Finetunes||get_api_projects_project_id_tasks_task_id_finetunes.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes`|POST|Create Finetune||post_api_projects_project_id_tasks_task_id_finetunes.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}`|GET|Get Finetune||get_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetunes/{finetune_id}`|PATCH|Update Finetune||patch_api_projects_project_id_tasks_task_id_finetunes_finetune_id.md|
|`/api/finetune_providers`|GET|List Finetune Providers||get_api_finetune_providers.md|
|`/api/finetune/hyperparameters/{provider_id}`|GET|List Finetune Hyperparameters||get_api_finetune_hyperparameters_provider_id.md|
|`/api/projects/{project_id}/tasks/{task_id}/finetune_dataset_info`|GET|Get Finetune Dataset Info||get_api_projects_project_id_tasks_task_id_finetune_dataset_info.md|
|`/api/download_dataset_jsonl`|GET|Download Dataset JSONL||get_api_download_dataset_jsonl.md|

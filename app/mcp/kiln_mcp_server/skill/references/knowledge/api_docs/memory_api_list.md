# Memory API

The Kiln assistant's durable memory for a project (save, list, get, update, delete, summary).

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/memories`|GET|List Memories|List memory summaries newest-first. content_length 0 means the overview is the whole memory. Truncat...|get_api_projects_project_id_memories.md|
|`/api/projects/{project_id}/memories`|POST|Save Memory|Save a memory: a note for agents working on the project.  It has an overview, a scope, and optional ...|post_api_projects_project_id_memories.md|
|`/api/projects/{project_id}/memories/summary`|GET|Memory Summary|Cheap per-scope orientation (counts, newest timestamp, tag cardinalities) with no record content. Ca...|get_api_projects_project_id_memories_summary.md|
|`/api/projects/{project_id}/memories/by_ids`|GET|Get Memories|Fetch full memory records by id. Unknown ids are omitted from the result.|get_api_projects_project_id_memories_by_ids.md|
|`/api/projects/{project_id}/memories/{memory_id}`|PATCH|Update Memory|Correct a memory's overview, content, tags or scope.|patch_api_projects_project_id_memories_memory_id.md|
|`/api/projects/{project_id}/memories/{memory_id}`|DELETE|Delete Memory|Hard-delete a memory. For junk, wrong, or obsolete memories; use update instead if the memory should...|delete_api_projects_project_id_memories_memory_id.md|

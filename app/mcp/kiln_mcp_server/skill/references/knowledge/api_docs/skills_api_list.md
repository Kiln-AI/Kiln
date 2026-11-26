# Skills API

Create and manage agent skills within projects.

|Endpoint|Method|Name|Description|Details File|
|-|-|-|-|-|
|`/api/projects/{project_id}/skills`|GET|Get Skills|List the project's skills.|get_api_projects_project_id_skills.md|
|`/api/projects/{project_id}/skills`|POST|Create Skill|Create a skill in the project from a name, description and SKILL.md body.|post_api_projects_project_id_skills.md|
|`/api/projects/{project_id}/skills/{skill_id}`|GET|Get Skill|Get one skill's name, description and archived flag.|get_api_projects_project_id_skills_skill_id.md|
|`/api/projects/{project_id}/skills/{skill_id}`|PATCH|Update Skill|Archive or unarchive a skill. A skill can't be edited: create a new skill instead.|patch_api_projects_project_id_skills_skill_id.md|
|`/api/projects/{project_id}/skills/{skill_id}/content`|GET|Get Skill Content|Get a skill's SKILL.md: the full file and its body.|get_api_projects_project_id_skills_skill_id_content.md|

---
name: working_with_project_files
description: Working with a Kiln project's files on disk - read them directly when that is faster than the API, make every write through the API, and never change in place a prompt, skill or run config that measurements depend on. Read it before you open, search or change a file in a Kiln project folder.
---

# Working with a project's files

A Kiln project is a folder of plain files. When you run on the same machine
as Kiln, or the user shares the folder with you, you can often see those
files. Three rules cover how to use them.

## Where the files are

`GET /api/projects` (`references/knowledge/api_docs/get_api_projects.md`)
gives each project's `path`: the project's `project.kiln` file. Its folder
holds one folder per kind of child, and each child is a folder named
`<id> - <name>` with one `.kiln` file of JSON inside:

```
project.kiln
tasks/<id> - <name>/task.kiln
tasks/<id> - <name>/runs/<id>/task_run.kiln
tasks/<id> - <name>/prompts/  run_configs/  evals/  specs/  eval_inputs/  ...
skills/  code_tools/  documents/  external_tool_servers/  assistant_memory/  ...
```

The ids in the folder names are the ids that the API takes.

## Reading files directly is fine

When reading, searching or listing the files is faster than the API, do
that. Examples: search every task run for a phrase with `grep`; count the
runs that have a tag; read a long prompt or a trace in full; find which
run configs name a tool. The API stays the way to read what Kiln computes
and does not store as a file in that form: scores and summaries, eval
progress, the rendered prompt, model and provider details, the state of a
job.

A file that you read can change under you: the app, a background job or a
teammate's git pull may write it. Read it again before you rely on an old
read.

## Writes always go through the API

Never create, edit, move or delete a file in the project folder yourself,
not even a small fix to one field. The API runs the validation checks and
the side effects that a write needs: ids, the links between parent and
child, the checks of each schema, and the secrets that must stay out of the
files. A file written by hand can make the whole project fail to load
in Kiln. When no endpoint does the change, say so to the user, or give the
app link of the page that does it (the end of `SKILL.md`).

## Respect immutability

Prompts, skills and run configs are linked to the history of eval
measurements. A score was measured on one exact prompt, skill and run
config. Changing one in place makes every measurement on it wrong without
a trace. So never change one in place, through the API or otherwise: add a
new copy (a new prompt, a new skill, a new run config that names them), so
the history is kept. The knowledge files say how to make each copy:
`references/knowledge/prompt_rewrite.md`,
`references/knowledge/adding_skills.md`,
`references/knowledge/model_create_configs.md`.

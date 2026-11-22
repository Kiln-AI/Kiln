---
title: Skills
description: Skill bundles that a run config attaches as tools - a new skill, a new version of an inherited skill, or a skill attached or dropped on a new run config.
reviewed: 2026-11-13
api_docs:
  - references/knowledge/api_docs/get_api_projects_project_id_skills.md
  - references/knowledge/api_docs/get_api_projects_project_id_skills_skill_id.md
  - references/knowledge/api_docs/get_api_projects_project_id_skills_skill_id_content.md
  - references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md
  - references/knowledge/api_docs/patch_api_projects_project_id_skills_skill_id.md
---

# Skills

## What it is

A skill is a document that the agent loads when it decides to. It has three
tiers, and each tier costs context only when the agent reaches it:

1. The **description**, in the tool list of every call while the skill is
   attached, opened or not. It decides whether the agent opens the skill.
2. The **`SKILL.md` body**, which loads when the agent opens the skill.
3. The **`references/` files**, each loaded on its own when the agent asks
   for it by path.

A run config attaches a skill as a tool, with the id
`kiln_tool::skill::<skill_id>` in `tools_config.tools`. Everything that the
baseline attaches is part of what the tuner can change, the inherited
skills too.

## How to change it

- **Read** the skills: `list_skills`, `get_skill`, and `get_skill_content`
  for the `SKILL.md` of one skill.
- **A new skill** is a bundle that the builder writes in its scratch folder
  and installs with the `install_skill_bundle` tool of the skill installer.
  The skill installer is not a gateway operation. The result gives the
  `tool_id` to attach.
- **A new version of an inherited skill**: export it with
  `export_skill_bundle`, change the copy, and install it under a new name,
  with the old skill's id in `derived_from_ids`. On the new run config,
  attach the new version and drop the old one.
- **Attach or drop** a skill: create a new run config with
  `create_run_config`, with the changed `tools_config.tools`.
- **A skill that was never attached** and is not needed can be archived
  with `archive_skill`.

Rules of the object:

- **A skill is immutable after install.** A change is a new version with a
  new name. Each name can be installed once.
- **The install is atomic.** A refused bundle writes nothing, and the
  refusal lists every problem at once.

## Limits

- A name has at most 64 characters, lower case with `-`. The description has
  1 to 1,024 characters.
- At most 512 KB for one file, and 2 MB for one bundle. Text files only in
  `references/`.
- No value from a train item goes into a skill. Code compares each new
  version with the version that it replaces, and searches it for copies of
  train content.
- Whether a model opens a skill depends on the model. A probe can answer it
  for this model before a skill arm is measured.
- When the parent's output mode sends the schema as a tool
  (`function_calling`, `function_calling_weak`, or `default` outside Ollama
  and Docker Model Runner), Kiln refuses every call once a tool or a skill
  is attached. Set the mode on the same run config by the fallback of
  [model](references/levers/model.md), step 4, and list it in `change`. The lever
  [output_mode](references/levers/output_mode.md) gives the modes.

## See also

- The `kiln-harness-tuner-experiment-build` skill, and its
  `references/skill-authoring.md`: the bundle layout, the `SKILL.md`
  contract, the clone and rewrite procedure, and the install.
- The `kiln-task-setup` skill: the skill payloads, and the tool id forms.

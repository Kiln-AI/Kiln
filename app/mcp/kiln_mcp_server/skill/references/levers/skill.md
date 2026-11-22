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
baseline attaches is part of what you can change, the inherited skills
too.

## How to change it

- **Read** the skills:
  `references/knowledge/api_docs/get_api_projects_project_id_skills.md`,
  `references/knowledge/api_docs/get_api_projects_project_id_skills_skill_id.md`,
  and
  `references/knowledge/api_docs/get_api_projects_project_id_skills_skill_id_content.md`
  for the `SKILL.md` of one skill.
- **A new skill**: create it with
  `references/knowledge/api_docs/post_api_projects_project_id_skills.md`
  (`name`, `description`, `body`). The tool id to attach is
  `kiln_tool::skill::<skill_id>`. The Kiln API takes no `references/`
  files: a skill with reference files is built when running Kiln Harness
  Tuner, which installs a whole bundle.
- **A new version of an inherited skill**: read its content, change the
  copy, and create it under a new name, with the old skill's id in
  `provenance.derived_from_ids`. On the new run config, attach the new
  version and drop the old one. The content endpoint returns the body only,
  so a new version made this way over the API loses the inherited skill's
  reference files. A new version that keeps them is built when running Kiln
  Harness Tuner.
- **Attach or drop** a skill: create a new run config with
  `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_run_configs.md`,
  with the changed `tools_config.tools`.
- **A skill that was never attached** and is not needed can be archived with
  `references/knowledge/api_docs/patch_api_projects_project_id_skills_skill_id.md`.

Rules of the object:

- **A skill is immutable after it is created.** A change is a new version
  with a new name. Use each name once.

## Limits

- A name has at most 64 characters, lower case with `-`. The description has
  1 to 1,024 characters.
- A bundle that Kiln Harness Tuner installs has at most 512 KB for one file,
  and 2 MB for one bundle. Text files only in `references/`.
- No value from a train item goes into a skill (the leak rules of
  `references/knowledge/train_val_test.md`). Compare each new version with
  the version that it replaces yourself, and search it for copies of train
  content.
- Whether a model opens a skill depends on the model. A quick check can
  answer it for this model before a skill experiment is measured.
- When the parent's output mode sends the schema as a tool
  (`function_calling`, `function_calling_weak`, or `default` outside Ollama
  and Docker Model Runner), Kiln refuses every call once a tool or a skill
  is attached. Set the mode on the same run config by the fallback of
  [model](references/levers/model.md), step 4, and record it as part of the
  change. The lever [output_mode](references/levers/output_mode.md) gives
  the modes.

## See also

- `references/knowledge/adding_skills.md`: the skill endpoints, the name
  limits, and how to attach a skill to a run config.
- `references/knowledge/run_an_experiment.md`: how to measure the change,
  judge it and keep it.

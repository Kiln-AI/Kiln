---
status: complete
---

# Agent API Info

We want to add some APIs designed specifically for our chat agent.

Design goals:
- provide the agent data it needed, while being token efficient. That typically means name, ID, and only really key info. Don’t flood context with irrelevant data. I give rough guidance for level of detail below, but design goal is to review actual models and really dial this in.
- The agent shouldn’t miss anything because it doesn’t know it exists. How it would have to make 20 API calls to understand a project, doesn’t always, and can miss obvious suggests (looks like there’s a RAG tool to solve this, but it’s not in your run config!)
- eliminate cases where the agent must make many many calls to get needed data. Loops should be in code, not in LLM land.

## agent_overview API

An api that get’s the agent an overview of the task in one shot. The agent should call this on startup most of the time. This gives it an overview of what exists, so it doesn’t miss anything, and can make fewer “list” calls.

This focuses on current task - should not have information about other tasks/projects.

Data: 
- current project: name, description, etc
- current task: name, description, json schemas, prompt (truncated to 300 words if needed).
- Dataset
  - count of dataset items
  - dict of tag to count
  - dict of source (human, import, etc) to count
  - dict of overall-rating to count (none, 5-star, 4-star, etc)
- Docs & Search
  - Docs: how many docs does this project have, dict of doc-tag to count
  - Search tools: list of each search tool (name, ID, etc)
- Prompts: list of prompts: name, ID, type
- Evals/Specs: 
  - list of specs: eval id, name, description, template, priorty
  - list of evals: eval id, name, description, template, has_default_judge
- Tools: list of tool servers with ID, description, tool count. Don’t list sub-tools (goal to not make MCP server calls to populate this, and it can get long fast).
- Run configs: default_run_config_id (can be null) and list of run configs (name, model, prompt ID, description, list of tool IDs, list of skill IDs, type, is favourited 
- Fine-tunes: list of fine tunes. Each with name, base model, id
- Skills: list of skills. Name, description, ID

What else? This is quick scan. Look at all APIs and suggest missing areas.

Note: 
- created_at should be included in most cases, I forgot to list. 
- is_favourited and priority should always be included if an option on the model.
- for models you can archive, archived elements should be excluded from the lists, but archived_count should be set so it knows there are some.
- empty values should still have the key and a value, eg`prompts: {}` or`prompts: []` or `description: null`. This API will evolve over time, and the agent should be able to tell the difference between “checked and empty” and “older client not populating this value”.

## all_tasks

An API that lists all projects, and tasks under each project. Names, IDs, descriptions, but not prompts.

Not called every time by agent, but useful when browsing whole workspace

- Projects: list of all projects
  - name, description, created_at, etc
  - tasks: lists of all tasks under that project
    - name, description, created_at, etc. Truncated task prompt (100 words)

## Eval Results

To get evals results for a task, the agent needs to make a ton of calls. Many `"/api/projects/52324324234234/tasks/319197374381/evals/282432666591/eval_config/149427653283/score_summary"` calls.

Should have a wrapper API that just returns them all (same results structure, but iterate over all run configs and evals for them, without many calls).
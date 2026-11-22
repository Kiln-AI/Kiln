---
name: establish_intent
description: |
  The steps for a request whose mode is unclear: questions to ask, routing examples, and what to offer a user who is unsure. The routing table itself is in SKILL.md.
---
# Mode: Establish Intent

Read this file when the user's request is unclear, or fits more than one mode of the routing table in `SKILL.md`. The goal is to get the user into the right mode quickly.

## Route before discovery

When the intent is clear enough to pick a mode, read that mode file before any API call, including project and task discovery. Task Context Discovery is defined inside each mode and runs after the mode is read. Do not call `call_kiln_api` from this file.

## Routing examples

When the user's message is clear about their intent, skip the questions and route directly:

- "hi" / "hello" / "who are you" / "what can you do" / "help" → Learn About Kiln (give a short overview of what Kiln can do, from the list below)
- "Create a new task for email classification" → Project Operations
- "My agent is hallucinating, make it better" → Improve Task
- "What are the results of this run?" / "Show me this run" / "What's in this run?" → Project Operations (inspecting one specific dataset run on a `http://localhost:8757/dataset/{project_id}/{task_id}/{run_id}/run` page — not enumerating run configs)
- "List my run configs" / "which one is starred" / "show me my models on this task" → Improve Task (inventory + assessment of what's already deployed; not Project Operations, which is for editing project resources)
- "What is an eval?" → Learn About Kiln
- "How much does GPT-5 cost?" → Improve Task (model selection)
- "I want to create an eval to track hallucinations" → Improve Task (quality-motivated eval creation)
- "My model outputs are too long, I need an eval for that" → Improve Task (quality-motivated eval creation)
- **Eval vs. error contrast:** user names a quality problem and asks for an eval → Improve Task; user names an error message and asks what it means → Learn About Kiln, even if a new eval is part of the eventual fix.
- "How do I incorporate eval feedback into my prompt?" → Improve Task (prompt improvement)
- "What is Kiln Pro?" / "Tell me about evals" / "Who made Kiln?" / "What company built this?" / "What team runs Kiln?" → Learn About Kiln (feature or product explanation)
- "I'm using GLM 5" / "What's a good model for me?" (no task named) → Improve Task; if task is unclear, ask which task in the first turn rather than answering generically
- "Compare my eval scores" / "How did my eval go?" / "Which model is best?" / "Show me the scorecard" → Improve Task (eval score analysis)
- "Upgrade / change / swap my model" / "faster model for my task" / "cheaper run config" → Improve Task — if the user names a project/task that happens to include words like "Eval Builder" or "Refine Eval" in its name, treat them as user-named entities, not internal feature references
- "Fine-tune my model" / "create a fine-tune job" / "train a custom model" / "should I fine-tune?" / "check my fine-tune status" → Improve Task (fine-tuning is a quality/cost improvement lever)
- "optimize my model" / "make my agent better" / "which model/prompt is best?" → Improve Task (compare candidates with an experiment, read the eval scores, recommend the winner)
- "are sub-agents better for my task?" / "should I split this big prompt?" → Improve Task (sub-agent setup + experiment comparison)
- "add 3 evals to my task" / "what should I be measuring?" → Improve Task (discuss what to measure, route to the Eval Builder)
- "use Jev" / "TypeSafe AI" / "a classification model as my judge" / "a cheaper judge for pass/fail" → Improve Task (read `references/knowledge/typesafe_jev.md`); "what is Jev?" → Learn About Kiln
- "Stuck on API keys" / "can't connect my provider" / "on the provider setup screen" / desktop app install help → Learn About Kiln (provider setup / troubleshooting)
- "I'm getting an error when..." / "no eval config found" / "no eval found" / "my eval won't run" / "my run is stuck pending" → Learn About Kiln (runtime/setup error — even when the error message names a Kiln resource the user could create, the user is asking *what does this error mean and how do I fix it*, not *help me improve quality*)
- "make me a sub agent" / "create a Subagent" / "wire this task as a tool" / "delegate to another task" / "how do I add a Subagent" / "how do I make a sub agent" / "how do I wire" → Improve Task (parent task in context) or Project Operations (creating from scratch) — these all mean Kiln Task as Tool; do NOT enumerate Kiln features and ask the user to pick which kind they mean. *"How do I add/make/wire"* phrasing is **action-shaped**, not a feature explanation — route to Improve Task even though it starts with "how do I".
- "what is a sub-agent" / "how do Subagents work" / "explain Multi-Actor" → Learn About Kiln
- "add a tool" / "connect MCP" / "set up MCP" / "wire up <Github | Slack | Firecrawl | Python | filesystem>" / "I want web search" / "let it run code" / "I need stock quotes" / "agent needs to call our API" → Improve Task (adding capability to an existing task; read `references/knowledge/tools.md`, and `references/knowledge/subagents.md` for a sub-agent)
- "what is MCP" / "how do tools work in Kiln" / "what tools can I add" / "explain tool servers" → Learn About Kiln

Only route from an example when the intent is unambiguous. When in doubt, ask.

**"What is X" / "How does Y work" routes to Learn About Kiln.** Answer a feature question from the mode and its knowledge files, never from what you remember.

**Any factual question about Kiln — features, company, team, origin, pricing, policies — routes to Learn About Kiln.** If Learn About Kiln doesn't have the answer, say so; don't fabricate.

## Suggested questions

Use these to understand the user's goal. Skip any that are already answered.

1. **"What are you trying to accomplish?"** — The core question. Listen for keywords that map to modes.
2. **"Are you building something new, improving something existing, or learning about Kiln?"** — Maps directly to the three modes.
3. **"Which project and task are you working with?"** — Establishes context for Project Operations and Improve Task.

**Example of a request that fits many modes:** if the user wants to create an eval or edit a prompt *because* of a quality problem (bug, hallucination, inaccuracy, eval results), route to **Improve Task** — the eval or prompt work is a means to an improvement goal. Route to **Project Operations** only when the user is doing standalone setup (e.g., "set up evals for my new task").

## What Kiln can help with

When the user is unsure, offer these examples:

- **Build a new AI agent** — create tasks, write prompts, set up initial configs
- **Improve quality** — audit prompts, create evals, run experiments, optimize
- **Reduce cost or latency** — a cheaper or faster model, a shorter prompt, another provider
- **Compare models** — research pricing and capabilities, run benchmarks
- **Fine-tune a model** — create dataset splits, launch training jobs, check status, use the fine-tuned model in a run config
- **Troubleshoot errors** — provider setup, API issues, configuration problems
- **Learn about Kiln features** — evals, Eval Builder, RAG, tools, skills
- **Review project status** — see what's set up, identify gaps, get recommendations

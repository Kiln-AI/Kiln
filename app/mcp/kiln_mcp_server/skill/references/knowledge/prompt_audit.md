---
name: prompt_audit
description: |
  Systematic prompt review checklist covering clarity, output format, edge cases, examples, persona, constraints, and token efficiency. Loaded by the Improve Task mode and referenced by other knowledge files.
---
# Prompt Audit

Systematic review of the task instruction and prompt config to find obvious problems before spending money on model upgrades. Always audit first — it catches structural issues a model upgrade can't fix.

## Context

This knowledge is used when eval scores are low across ALL configs (the base prompt is the common factor, not the model), or when the user asks for a general review with no specific direction.

## API Docs

Load the relevant endpoint doc **before** making each API call. Use the domain catalogs below to find any endpoint not listed in the table.

| Domain | Catalog |
|--------|---------|
| Prompts | `references/knowledge/api_docs/prompts_api_list.md` |
| Tasks | `references/knowledge/api_docs/tasks_api_list.md` |
| Specs | `references/knowledge/api_docs/specs_api_list.md` |
| Evals | `references/knowledge/api_docs/evals_api_list.md` |

| Endpoint | Load |
|----------|------|
| GET task (instruction, schemas) | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md` |
| PATCH task (instruction, schemas) | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id.md` |
| GET prompts list | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_prompts.md` |
| PATCH prompt | `references/knowledge/api_docs/patch_api_projects_project_id_tasks_task_id_prompts_prompt_id.md` |
| POST build prompt with examples | `references/knowledge/api_docs/post_api_projects_project_id_tasks_task_id_build_prompt_with_examples.md` |
| GET generated prompt | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md` |
| GET list specs | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_specs.md` |
| GET list evals | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_evals.md` |
| GET run config eval scores | `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_run_configs_run_config_id_eval_scores.md` |

## How to Audit a Prompt

### Read the Current Task and Prompt

Saved prompts are already available in `agent_overview.prompts.items`. For the full (untruncated) instruction and schemas, and the generated prompt text:

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md`, then:
`call_kiln_api("GET", "/api/projects/{pid}/tasks/{tid}", jq_filter="{instruction, input_json_schema, output_json_schema}")` — Read the full `instruction` field and I/O schemas.

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md`, then:
`call_kiln_api("GET", "/api/projects/{pid}/tasks/{tid}/gen_prompt/simple_prompt_builder")` — See the full prompt as it would be sent to the model.

### Audit Checklist

Go through each item. Collect findings.

**1. Clarity & Specificity**
- [ ] Is the task goal stated in the first 1-2 sentences?
- [ ] Would someone unfamiliar with the domain understand what to do?
- [ ] Are there ambiguous terms that could be interpreted multiple ways?
- [ ] Are acronyms and domain terms defined?

**2. Output Format**
- [ ] Is the expected output format explicitly described?
- [ ] Does it match the task's `output_json_schema`?
- [ ] Are enum values / allowed categories listed?
- [ ] Are there length constraints?

**3. Edge Cases & Boundaries**
- [ ] What happens with ambiguous inputs?
- [ ] What should the agent do when it's unsure?
- [ ] Are there inputs that should be rejected or handled specially?
- [ ] Is there a "default" or "fallback" behavior defined?

**4. Examples**
- [ ] Are there any examples? (even 1-2 help significantly)
- [ ] Do the examples cover both typical and edge cases?
- [ ] Are the examples consistent with the instruction?

**5. Persona & Tone**
- [ ] Does the agent know its role/persona?
- [ ] Is the expected tone described (if output is user-facing)?
- [ ] Are there dos and don'ts for communication style?

**6. Constraints & Guardrails**
- [ ] Is forbidden content addressed?
- [ ] Are there safety boundaries?
- [ ] Is the agent told what NOT to do?

**7. Reasoning & in-context examples (never a recommended method)**
- [ ] Never propose CoT prompt templates or `thinking_instructions` — reasoning belongs at the run config's thinking level, not in the prompt text
- [ ] Never propose few-shot / multi-shot examples as a fix — that's not a lever this skill recommends; close ambiguity with explicit rules, definitions, and format instead
- [ ] If the prompt already carries CoT/thinking instructions, flag them as a removal candidate (test removal as an experiment)

**8. Prompt Length & Token Efficiency**
- [ ] Is the prompt unnecessarily verbose?
- [ ] Could sections be compressed without losing meaning?
- [ ] Are there large copy-pasted blocks that could be summarized?
- [ ] Is the prompt under ~2000 tokens?

## Common Anti-Patterns

| Anti-Pattern | Fix |
|-------------|-----|
| "Be helpful and accurate" (too vague) | Replace with specific criteria: "Classify as X if Y, Z if W" |
| No output format specification | Add explicit format: "Respond with JSON containing..." |
| Examples contradict instruction | Align examples with rules, or remove them |
| Instruction says "do everything" | Scope to the specific task; remove aspirational fluff |
| Very long prompt with repetition | Deduplicate; use structured lists instead of paragraphs |
| No edge case guidance | Add a "When unsure..." section |
| Telling the model what it IS instead of what to DO | Focus on actions and outputs, not identity |

## Reporting Findings

**Lead with the recommendation** — what to fix first and why — then follow with the categorized findings. The recommendation must appear before audit details so the user gets the actionable plan even if the message truncates.

Present findings as a short prioritized list:
- **Critical** (likely causing failures): missing output format, contradictory examples
- **Important** (likely reducing quality): no edge case guidance, vague instructions
- **Nice to have** (marginal improvement): persona refinement, tone instructions

For each finding, suggest a specific fix. Return findings and proposed fixes to the caller — the calling mode or knowledge file decides what to do next (e.g., edit the prompt, swap models).

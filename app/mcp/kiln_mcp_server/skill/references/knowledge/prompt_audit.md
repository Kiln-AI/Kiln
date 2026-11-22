---
name: prompt_audit
description: |
  Prompt review checklist covering clarity, output format, edge cases, examples, persona, constraints, reasoning and length, each group with the knowledge document for that problem. Read it to check a new prompt, or when the user asks for a review of a prompt. It is not the first step of an improvement.
---
# Prompt Audit

A review checklist for the task instruction and a prompt. It has two uses:

- **A new prompt.** `references/knowledge/create_task.md` reads it before a starter prompt is drafted.
- **A user who asks for a review** of a prompt, with no other direction.

It is not the first step of an improvement. To make an agent better, start from `references/modes/improve_task.md`: the evidence of the agent and its train items decides what to change, through the playbooks. A finding of this checklist is a hypothesis to measure (`references/knowledge/run_an_experiment.md`), not a fix to apply in place: a change is a new saved prompt and a new run config (`references/levers/prompt.md`).

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

## How to Audit a Prompt

### Read the Current Task and Prompt

Saved prompts are already available in `agent_overview.prompts.items`. For the full (untruncated) instruction and schemas, and the generated prompt text:

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id.md`, then:
`call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}", jq_filter="{instruction, input_json_schema, output_json_schema}")` — Read the full `instruction` field and I/O schemas.

Read `references/knowledge/api_docs/get_api_projects_project_id_tasks_task_id_gen_prompt_prompt_id.md`, then:
`call_kiln_api("GET", "/api/projects/{project_id}/tasks/{task_id}/gen_prompt/simple_prompt_builder")` — See the full prompt as it would be sent to the model.

### Audit Checklist

Go through each item. Collect findings. Each group names the knowledge document for that problem: when a finding is the problem the document covers, follow the document for what to try.

**1. Clarity & Specificity** — a requirement that the prompt does not state: [requirement missing from the prompt](references/improving_agents/playbooks/requirement-missing-from-the-prompt.md)
- [ ] Is the task goal stated in the first 1-2 sentences?
- [ ] Would someone unfamiliar with the domain understand what to do?
- [ ] Are there ambiguous terms that could be interpreted multiple ways?
- [ ] Are acronyms and domain terms defined? Ambiguous terms and categories spelled out, so the model does not guess?

**2. Output Format** — [output contract not met](references/improving_agents/playbooks/output-contract-not-met.md), [state the output contract](references/improving_agents/techniques/state-the-output-contract.md), and the lever `references/levers/output_mode.md`
- [ ] Is the expected output format explicitly described?
- [ ] Does it match the task's `output_json_schema`?
- [ ] Are enum values / allowed categories listed?
- [ ] Are there length constraints?

**3. Edge Cases & Boundaries** — [wrong scope or refusal](references/improving_agents/playbooks/wrong-scope-or-refusal.md)
- [ ] What happens with ambiguous inputs?
- [ ] What should the agent do when it's unsure?
- [ ] Are there inputs that should be rejected or handled specially?
- [ ] Is there a "default" or "fallback" behavior defined ("when unsure, do X")?

**4. Examples** — an example in a prompt uses invented values, never the values of a train item: the leak rules of `references/knowledge/train_val_test.md`
- [ ] Are there any examples? (even 1-2 help significantly)
- [ ] Do the examples cover both typical and edge cases?
- [ ] Are the examples consistent with the instruction?

**5. Persona & Tone**
- [ ] Does the agent know its role/persona?
- [ ] Is the expected tone described (if output is user-facing)?
- [ ] Are there dos and don'ts for communication style?

**6. Constraints & Guardrails** — [policy as step-by-step procedures](references/improving_agents/techniques/policy-as-step-by-step-procedures.md), [decline rules paragraph](references/improving_agents/techniques/decline-rules-paragraph.md)
- [ ] Is forbidden content addressed?
- [ ] Are there safety boundaries?
- [ ] Is the agent told what NOT to do? Are there explicit do / don't rules?

**7. Reasoning & in-context examples (never a recommended method)** — reasoning is a setting of the run config: the lever `references/levers/params.md`
- [ ] Never propose CoT prompt templates or `thinking_instructions` — reasoning belongs at the run config's thinking level, not in the prompt text
- [ ] Never propose few-shot / multi-shot examples as a fix — that's not a lever this skill recommends; close ambiguity with explicit rules, definitions, and format instead
- [ ] If the prompt already carries CoT/thinking instructions, flag them as a removal candidate (test removal as an experiment)

**8. Prompt Length & Token Efficiency** — the length that is a problem, and what to do about it: [very long prompt](references/improving_agents/smells/very-long-prompt.md), [structure a long prompt](references/improving_agents/techniques/structure-a-long-prompt.md), [prune one group at a time](references/improving_agents/techniques/prune-one-group-at-a-time.md)
- [ ] Is the prompt unnecessarily verbose? Is there filler that changes no behaviour ("be helpful and accurate", identity-only phrasing)?
- [ ] Could sections be compressed without losing meaning?
- [ ] Are there large copy-pasted blocks that could be summarized?

**9. Measurement**
- [ ] Does an eval measure each failure that the review found? A failure with no eval is a gap: name it, and add an eval only when the user agrees (`references/knowledge/create_spec.md`).

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

For each finding, suggest a specific fix. A complete review usually spans several groups (format, definitions, constraints, edge cases, measurement); "add output constraints" alone is rarely the whole answer. Return findings and proposed fixes to the caller — the calling mode or knowledge file decides what to do next.

# `/spec implement` — Implement Project

Implement the active project. Routes to single-phase or full implementation.

## Pre-Checks

### Determine Active Project

Read `.specs_skill_state/current_project.md`. If no active project, ask the user to specify one.

### Verify Spec Complete

Check that all spec artifacts through `implementation_plan.md` have `status: complete`:

- project_overview.md
- functional_spec.md
- ui_design.md (if exists)
- architecture.md
- components/ (if exists)
- implementation_plan.md

If any are missing or `status: draft`:

> Project spec is incomplete. The following artifacts need attention:
> - [missing/draft artifacts]
>
> Use `/spec continue` to finish speccing before implementing.

## Routing

- `/spec implement` (no args): Ask "Implement next phase or all remaining phases?"
- `/spec implement next` or `/spec impl next`: Single phase
- `/spec implement all` or `/spec impl all`: All remaining phases
- `/spec implement phase N` or `/spec impl phase N`: Specific single phase

## Single Phase Implementation

Implement one phase autonomously. The coding agent works without user assistance from start to finish.

### Coding Persona

You are a very skilled senior engineer IC. Your code:

- Explains itself through great naming and composition
- Uses comments only for external constraints, not to describe poorly structured code
- Is test-driven: tests that catch real breakage, don't need constant refactoring, target 95%+ coverage, reuse test helpers

You're willing to flag when a requirement leads to bad technical outcomes — but you don't re-litigate plan-level decisions that were already confirmed during speccing.

### Implementation Loop

1. **Read the implementation plan** and identify the target phase
2. **Read spec and architecture docs** for context
3. **Write phase plan** to `/phase_plans/phase_N.md`:
   - Overview: what this phase accomplishes and why
   - Steps: ordered, specific. Files to change, exact changes, code snippets for signatures
   - Tests: specific automated test cases by name and what they verify
   - Completion criteria: checklist of what must be true when done
4. **Build the code** per the phase plan
5. **Run automated checks** (lint, format, type-check, build). Follow project-specific commands from system prompt. Iterate until clean.
6. **Write tests** per the phase plan's test section
7. **Run tests**. Iterate until passing.
8. **Run automated checks again** (tests/fixes may introduce lint/format issues). Iterate until clean.
9. **Self code-review via sub-agent**:
   - → Read [references/spawning_subagents.md](references/spawning_subagents.md) for how to spawn
   - Pass the prompt from [references/cr_agent_prompt.md](references/cr_agent_prompt.md) to the sub-agent
   - Include: "A coding agent just implemented phase N of [project]. Review the changes using `git diff`."
   - Iterate per CR Iteration Loop below
10. **Run automated checks one final time** (CR fixes may introduce issues). Iterate until clean.
11. **Mark phase complete** in `implementation_plan.md` (toggle checkbox only)
12. **Stop and present summary** of what was built

### CR Iteration Loop

1. Spawn CR sub-agent with clean context. Pass the CR prompt from `cr_agent_prompt.md`.
2. CR returns feedback with severity labels (critical/moderate/mild).
3. If issues exist:
   - Fix each issue (or rarely, add a code comment explaining the technical rationale)
   - Spawn a new CR sub-agent, passing the same CR prompt plus `<prior_cr_feedback>` block
4. The re-review agent:
   - Verifies prior issues are addressed
   - Checks for new issues from fixes
5. Loop until CR returns clean.

### Non-Interactive Rule

The coding phase is autonomous. Don't stop to ask the user for help.

**One exception:** You discover a genuinely new technical constraint not known at design time that materially changes the plan (e.g., an API doesn't support an assumed operation, a framework has an undocumented limitation).

In this case — and only this case — pause and surface the issue to the user for a decision.

## Implement All

A lightweight coordinator that runs all remaining phases in sequence.

### Coordinator Process

1. Get next incomplete phase from `implementation_plan.md`
2. Spawn a sub-agent with clean context to run the single-phase implementation flow above
   - → Read [references/spawning_subagents.md](references/spawning_subagents.md) for how to spawn
   - Pass: phase number, project path, instruction to follow single-phase implementation
3. **Auto-commit**: `"Phase N implementation of [project name]\n\n[description of work in phase]"`
4. Show the phase summary from the subagent to the user
5. Continue to next phase (don't stop)
6. Loop until all phases complete

### Coordinator Context

The coordinator has minimal context — it just manages the loop. Each phase sub-agent gets clean context.

CR happens inside each phase's implementation loop, not at coordinator level.

### Passed to Phase Sub-Agents

For implement-all, pass the content of [references/coding_phase_prompt.md](references/coding_phase_prompt.md) to each phase sub-agent. This prompt contains the full single-phase implementation instructions.

## References

- [references/spawning_subagents.md](references/spawning_subagents.md) — How to spawn sub-agents
- [references/coding_phase_prompt.md](references/coding_phase_prompt.md) — Prompt passed to coding sub-agents
- [references/cr_agent_prompt.md](references/cr_agent_prompt.md) — Prompt passed to CR sub-agents

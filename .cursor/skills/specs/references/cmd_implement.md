# `/spec implement` — Implement Project

Implement the active project. The top-level agent acts as a strict manager/coordinator — it orchestrates sub-agents but never writes code or reviews it.

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

## Manager Role

The manager orchestrates the implementation process. It does NOT code, review code, run tests, or make technical decisions.

The manager's responsibilities:
- Spawn coding sub-agents and CR sub-agents at the right times
- Route CR feedback back to the coding agent
- Verify that commits actually landed (via `git status`)
- Surface phase summaries and roadblocks to the user
- Send minimal, well-structured prompts that point to reference files — not restate their content

## Single Phase Flow

If the target phase is already complete (checkbox checked in `implementation_plan.md`), tell the user and stop — don't re-implement it.

### Step 1: Spawn Coding Agent

Spawn a new coding sub-agent using the Initial Coding Prompt template below.

→ Read [references/spawning_subagents.md](references/spawning_subagents.md) for how to spawn sub-agents.

The coding agent returns either:
- A summary indicating it's ready for code review
- A roadblock message (see Escalation below)

### Step 2: CR Loop

1. Spawn a fresh CR sub-agent using the CR Agent Prompt template below
2. CR agent returns structured feedback with severity labels
3. If the review is clean: proceed to Step 3
4. If issues exist:
   - Resume the coding agent with the CR Feedback Prompt template, passing the CR output
   - Coding agent addresses issues and returns a summary
   - Spawn a new CR sub-agent, passing prior feedback in a `<prior_cr_feedback>` block
   - Repeat until CR returns clean

→ Read [references/spawning_subagents.md](references/spawning_subagents.md) for how to spawn sub-agents.

### Step 3: Commit

Resume the coding agent with the Commit Prompt template below. The coding agent commits all changes, marks the phase complete, and returns the commit message.

### Step 4: Verify

Run `git status` to confirm:
- Working tree is clean (no uncommitted changes)
- The commit exists

If `git status` shows uncommitted changes, resume the coding agent:

> Commit appears incomplete — `git status` shows uncommitted changes. Please commit all changes.

Verify again after.

### Step 5: Present Summary

Show the phase summary to the user.

## Implement All

Run all remaining phases in sequence:

1. Read `implementation_plan.md`, find all incomplete phases
2. For each phase: run the Single Phase Flow above
3. Between phases: show the phase summary, then immediately continue to next phase (don't stop to ask)
4. After all phases: present a final summary

If a target phase is already complete (checkbox checked), skip it.

## Prompt Templates

These are the exact prompts the manager sends to sub-agents. Use them verbatim, filling in the bracketed values.

### Initial Coding Prompt

```
You are a coding agent implementing a phase of a spec-driven project.

**Phase:** [N]
**Project specs:** [specs/projects/PROJECT_NAME/]

Read `skill/references/coding_phase_prompt.md` for your full instructions. Follow them precisely.

Return a short summary of what you built when implementation is complete and ready for code review.
```

### CR Feedback Prompt (resume coding agent)

```
A code reviewer found issues with your implementation. Address all feedback below, then run automated checks until clean.

Return a short summary of changes made when ready for re-review.

<cr_feedback>
[CR agent's output]
</cr_feedback>
```

### Commit Prompt (resume coding agent)

```
Your code has passed review. Commit all changes with a descriptive message summarizing the work done in this phase. Mark the phase checkbox complete in implementation_plan.md.

Return the commit message you used.
```

### CR Agent Prompt

```
Review code changes for phase [N] of the project at [specs/projects/PROJECT_NAME/].

Read `skill/references/cr_agent_prompt.md` for your full review instructions. Follow them precisely.
```

For re-reviews, append:

```
<prior_cr_feedback>
[Previous CR output]
</prior_cr_feedback>
```

## Escalation

The coding agent may surface a technical roadblock instead of a "ready for CR" summary. This happens when the coding agent's "one exception" rule triggers — a genuinely new technical constraint not known at design time.

When the manager receives a roadblock message:

1. Present the roadblock to the user and wait for a decision
2. Resume the coding agent with the user's decision
3. Continue the single-phase flow from wherever the coding agent left off

## References

- [references/spawning_subagents.md](references/spawning_subagents.md) — How to spawn and resume sub-agents
- [references/coding_phase_prompt.md](references/coding_phase_prompt.md) — Full instructions for coding sub-agents
- [references/cr_agent_prompt.md](references/cr_agent_prompt.md) — Full instructions for CR sub-agents

# `/spec cr` — Code Review

Structured, spec-aware code review. Aliases: `/spec cr`, `/spec code_review`.

## Key Principle

The CR agent never has the coding agent's context. Decisions must be captured in code and specs, not in context windows.

If something important is only in conversation history, that's a bug in the process.

## Determine Scope

- **No arguments**: Review `git diff` (unstaged + staged changes)
- **Given scope**: Review that scope (e.g., "review file X", "review phase 3", "review src/main.rs")

## Execution

Always run as a sub-agent — spawned fresh, no prior context from coding.

→ Read [references/spawning_subagents.md](references/spawning_subagents.md) for how to spawn sub-agents.

Pass the prompt from [references/cr_agent_prompt.md](references/cr_agent_prompt.md), plus scope description.

### Example invocation

> Spawn a code review sub-agent with the following task:
>
> "Review the git diff using the spec-driven development code review guidelines. The project is at [path]. Read the functional spec and architecture to verify implementation matches design."

## Re-Review

If the user provides prior CR feedback (or this is called from a loop), pass it as `<prior_cr_feedback>` to the CR sub-agent:

```
<prior_cr_feedback>
[Prior CR content here]
</prior_cr_feedback>
```

The CR prompt handles verification of prior issues.

## Post-Review

Present findings to the user:

> Code review complete:
>
> ### Critical (must fix)
> - [file:line] [description]
>
> ### Moderate (should fix)
> - [file:line] [description]
>
> ### Mild (consider fixing)
> - [file:line] [description]
>
> [Or: No issues found — implementation looks good!]

If issues exist and user wants fixes:

- User can fix themselves, then re-run `/spec cr` with prior feedback
- Or coding agent can address them, then re-run CR with prior feedback

The loop continues until clean.

## References

- [references/spawning_subagents.md](references/spawning_subagents.md) — How to spawn sub-agents
- [references/cr_agent_prompt.md](references/cr_agent_prompt.md) — Prompt passed to CR sub-agent

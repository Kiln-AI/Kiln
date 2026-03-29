# Spawning Sub-Agents

Explanation of the sub-agent pattern and how to use it across different tools.

## What and Why

Sub-agents are fresh agent contexts with no conversation history from the current session.

Use them when clean context matters:

- **Code review**: CR shouldn't see coding agent's thinking
- **Phase implementation**: Each phase starts fresh

The sub-agent sees only what you pass it (a prompt) plus the repo. No conversation history.

## What to Pass

- A prompt/task description (caller specifies this — typically a reference file's content)
- Optionally structured data like `<prior_cr_feedback>`

**Never pass conversation history.** The point is a clean context.

## Examples by Tool

### Claude Code

Use the `Task()` tool or equivalent sub-agent mechanism:

```python
Task("Review this code using the guidelines in skill/references/cr_agent_prompt.md")
```

### Cursor

Use Cursor's sub-agent spawning capability.

### Generic / Unknown

If the tool doesn't have explicit sub-agent support:

Approximate by:
1. Clearing context
2. Starting a new conversation with only the sub-agent prompt

This is less ideal since it can't run in parallel with the parent, but works for the clean context requirement.

## Resuming Sub-Agents

Some workflows need to send follow-up messages to an existing sub-agent
rather than spawning a fresh one. This preserves the agent's context.

Use when: the sub-agent needs to continue work it already started
(e.g., a coding agent addressing CR feedback on code it just wrote).

### Claude Code

When continuing prior subagent work, save the agent ID from the initial Agent call and resume it with:

Agent({ "resume": agent_id, "prompt": "Continue with the next step." })

### Cursor

Use Cursor's `resume` options

### Generic / Unknown

Generic tools typically don't support resuming — use a fresh spawn with accumulated context if needed.

### When to Resume vs. Fresh Spawn

- **Resume**: coding agent receiving CR feedback or commit approval (needs its prior context)
- **Fresh spawn**: CR agent (must NOT have coding context)

## Fallback Language

If unsure about tool capabilities, use:

> Use your sub-agent or task-spawning capability to start a fresh agent context with the following prompt:
>
> [prompt content]

The agent will use whatever mechanism is available.

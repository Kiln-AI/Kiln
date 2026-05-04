---
status: complete
---

# Multiturn Tasks

We are making `Task` able to be multiturn — i.e. allowing a `prior_trace` to be passed when creating a new trace, so the new trace continues the prior one. Conceptually similar to our current chat.

A task should be either single-turn or multiturn (an enum). The default is single-turn; existing tasks with no value should be treated as single-turn.

If a task is multiturn, its run page should be conceptually similar to the chat experience — allowing continuation of an existing trace, sending follow-up turns, etc.

## Linear

- Linear ticket: KIL-632
- Branch: `leonard/kil-632-feat-multiturn-task`

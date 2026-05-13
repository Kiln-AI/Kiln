---
status: complete
---

# Multiturn Trace Forking

We want to add the ability to fork a multiturn trace.

The way multiturn currently works: on a given turn, the `invoke` call takes in a `prior_trace`. The resulting `TaskRun` has a reference to its parent `TaskRun` (the one that the prior trace came from).

We want to:

1. Associate the blocks we show in the `/run` page multiturn UI (system, user, assistant, tool blocks) with the parent `TaskRun` id they come from.
2. Allow forking from there.

In the dataset page, we currently only show leaf nodes, so the parents are not surfaced — but they do exist in the filesystem hierarchy we persist to. We need to handle inconsistency / corruption gracefully (e.g. a parent run could be missing).

In the `/run` UI for the multiturn task, we should then show a forking button on each user block, allowing the user to send a new message instead of that user block (i.e. continue from the previous task run parent to the block in question).

This will likely require server-side traversal of the parent chain back up the hierarchy, matching each ancestor to its corresponding node in the current trace, etc.

## Linear

- Branch: `leonard/kil-632-feat-multiturn-task` (continuation of the multiturn task work)

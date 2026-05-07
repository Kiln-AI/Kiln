---
status: complete
---

# Multiturn Turn-Level Usage Tracking

In the multiturn case, we want to capture the token count / usage cost for each turn and persist that in the TaskRun trace (probably similar to the existing `is_error`, `error_message`, and `latency_ms` fields).

We also want a TaskRun-global sum of all turns' usage (price and tokens) as a separate field — possibly reusing the existing usage field on the TaskRun, but holding the sum across turns.

A little awkward: one turn is not necessarily one user-assistant message pair — a multiturn conversation can be seeded from a prior trace that already has those back-and-forths in it.

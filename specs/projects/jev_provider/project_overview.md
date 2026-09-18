---
status: draft
---

# Jev Provider (TypeSafe AI System One)

Add TypeSafe AI's Jev model as a Kiln provider. Jev is a new type of model: text (or JSON) input, but only structured output, and only a custom subset of structured output options (choice, score, noul). It has no text generation, no tools, and no multi-turn conversation. It returns typed answers with per-option probabilities and a confidence.

We want a Kiln task to be runnable against Jev when the task is compatible. It won't work on all Kiln tasks, but should work on some. Incompatible tasks are a runtime error when the user attempts to run them with a Jev model; the UI does not need to know in advance.

Limits on which tasks are compatible:

* Single turn only
* Only if the output is structured (JSON schema)
* Only for a subset of output JSON schemas: enums, bools (nouls), scores. We need a mapping from JSON schema into Jev's question format, good errors if incompatible, and the ability to map the result back out to JSON meeting the schema.

Rough shape of the work:

* Add Jev as a provider: UI, model list, the usual
* A new Jev `BaseAdapter`
* Routing the task adapter depending on provider/model (likely needs work, since today everything routes to LiteLLM)
* A set of helpers for the output (JSON schema → Jev questions → Jev answers → JSON)
* A formatter for the input (Kiln system prompt + user input → Jev "state"), possibly inside the Jev adapter
* Anything else needed for a solid implementation

Evals are a key use case: Kiln's eval output schemas (1-5 stars, pass/fail, pass/fail/critical) all fit Jev's question types, and Jev's native probabilities are what G-Eval currently approximates with logprobs.

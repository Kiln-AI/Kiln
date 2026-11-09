# Open Design Questions: Kiln Smart Harness

> **Status: unverified and not directional.**
> These are a research agent's thoughts and ideas, recorded while comparing other frameworks. They have **not** been reviewed or accepted. Treat every "lean" below as one person's opinion, not as a decision or requirement, unless the project owner has explicitly confirmed it.
> Factual claims about other frameworks are in `01-competitive-report.md`. Everything in this file that isn't a cited fact there is speculation.

Each item has: **Question**, **Context** (what others do, or why it came up), **Ideas / options**, and **Agent's lean (unverified)**.

---

## A. Shape of the abstraction

### A1. Wrap-style `next()` vs. before-only "return overrides"
- **Question:** should the main interface wrap the LLM call (`next(inputs, options)`, like HTTP middleware), or run before it and return overrides (the ALT VERSION in the rough design)?
- **Context:**
  - LangChain and Pydantic AI both offer *both* styles: node-style before/after hooks, plus wrap hooks that nest.
  - Only wrap (or after) hooks can post-process a response.
  - The rough design's own stacking example includes "check response doesn't contain secrets," which is a post-call check.
- **Ideas / options:**
  1. Wrap only.
  2. Wrap as the main interface, with a before-only shortcut that returns `{overrides}` / `{response}` / `None`.
  3. Before-only.
- **Agent's lean (unverified):** option 2.

### A2. What does a middleware return?
- **Question:** which result types exist?
- **Context:**
  - The rough design lists: immediate response (content / tool calls), overrides, do nothing, redirect to subagent (P2).
  - LangChain's `jump_to` adds "end" and "go to tools."
- **Ideas / options:**
  - `respond(content)`: skip the LLM, finish the turn.
  - `inject_context(...)`: run something, add the result to context, and continue to the LLM (see C1).
  - `tool_call(...)`: a synthetic tool call (see C1 for the risks).
  - `override(model, thinking, params, tools, instructions)`.
  - `passthrough`.
  - `handoff(subagent)` (P2).
  - `stop(reason)`, for guardrails.
- **Agent's lean (unverified):** keep the set small and explicit. It's probably worth having `inject_context` as separate from `tool_call`.

### A3. Composition: stack plus shared state vs. middleware calling middleware
- **Question:** how does a complex rule like "canned > 0.9 AND needs_smarter < 0.5" get expressed?
- **Context:** LangChain's `ModelRouterMiddleware` writes its decision, with probabilities, into agent state, and later hooks read it. The rough design suggests code middleware can call other middleware, the way code tools call tools.
- **Ideas / options:**
  1. Ordered stack where middleware can read and write a typed `run_state` (decisions with probabilities).
  2. A "composite" code middleware that calls other middleware explicitly.
  3. Both.
- **Agent's lean (unverified):** both. Shared state makes most cross-middleware conditions expressible in a plain stack.

### A4. Ordering semantics
- **Question:** should Kiln copy the common order (before in order, wrap nested with the first outermost, after reversed)?
- **Agent's lean (unverified):** yes, copy it exactly and document it. Users moving from other frameworks will expect it.

---

## B. When middleware runs

### B1. What is a "turn"?
- **Question:** "Run before each turn" could mean each user message, or each LLM call inside the tool loop. Which, or both?
- **Context:**
  - eve routes once per user turn; LangChain once per run.
  - AI SDK `prepareStep`, Mastra `processInputStep`, Pydantic `SelectModel` and ADK `before_model` run on every LLM call.
  - Cloudflare Think has both `beforeTurn` and `beforeStep`.
  - Anthropic says to keep one thinking configuration per assistant turn (a tool loop is one turn).
- **Ideas / options:** separate hook levels, `on_turn` (user message boundary) and `on_model_call` (each LLM step), plus maybe `on_tool_call`.
- **Agent's lean (unverified):**
  - Model and thinking routing, canned answers and first-turn actions belong at turn level.
  - The per-call level is for in-loop concerns.
  - A tool-level hook could be P2, but plan its shape now (Jev tool-call approval is already a common use elsewhere).

### B2. Can model or thinking change mid tool-loop?
- **Question:** should mid-turn escalation be allowed, e.g. switching to a stronger model after repeated tool failures?
- **Context:** Anthropic's one-thinking-config-per-turn rule. `langchain-router` switches models by agent phase (a tool failure goes back to the primary model).
- **Ideas / options:**
  1. Disallow mid-turn changes.
  2. Allow only when the provider constraints permit (same provider and same thinking config, or thinking off).
  3. Allow, and let the harness repair history.
- **Agent's lean (unverified):** option 2, behind validation, with a clear error.

### B3. Filters: declarative or code?
- **Question:** should a middleware config carry filters (`turn_number == 1`), or should that live only in code?
- **Context:** no framework reviewed has declarative filters; they all branch in code.
- **Ideas / options:**
  - Code only, with rich context available (`turn_number`, `is_first_turn`, `last_step_had_tool_error`, conversation length, current model, cache state).
  - Optional declarative `when`, so the UI can show when a middleware runs and decision-model calls can be skipped cheaply.
- **Agent's lean (unverified):** code first; a declarative `when` is a nice-to-have for the UI and for skipping calls.

---

## C. Correctness hazards

### C1. Fabricated tool calls vs. extended thinking
- **Question:** is `return {tool_call: get_user_info}` safe?
- **Context:**
  - With thinking on, Anthropic rejects a history where the final assistant message doesn't start with a thinking block.
  - LiteLLM silently drops `thinking` for that turn instead.
  - So "always call get_user_info on turn 1" combined with "route to xhigh thinking" could quietly cancel the thinking.
  - Unverified recollection: Gemini 3 has a similar check on function-call parts (thought signatures).
- **Ideas / options:**
  1. `inject_context`: the middleware runs the tool and the result goes into context (system or user side), not a fabricated assistant message.
  2. Allow synthetic tool exchanges only when thinking is off.
  3. Detect the conflict and warn or error.
- **Agent's lean (unverified):** option 1 as the default, with option 3 as a safety net. Verify the provider rules before deciding.

### C2. How middleware actions appear in traces and history
- **Question:** when middleware answers with canned text or injects context, what goes into the persisted conversation and the trace?
- **Context:** eve runs the routing decision in a `"use step"` helper so replays reuse the recorded decision.
- **Ideas / options:**
  - Record every middleware decision as a trace span: inputs, decision-model answers, probabilities, chosen action.
  - Mark canned responses as such in history.
  - Make replay deterministic by reusing recorded decisions.
- **Agent's lean (unverified):** record everything. It's also what makes evals possible (see E1).

### C3. Adversarial input
- **Question:** what stops a user from steering the decision model into a privileged route?
- **Context:** Jev is documented as not built for adversarial defense. TypeSafe and Wavect both put hard policy in code *before* probabilistic routing.
- **Agent's lean (unverified):** canned answers are low-risk because they're fixed text. Keep anything with side effects (refunds, account actions) behind code checks, and never trust a decision model alone for them.

---

## D. Decision trees and decision-model tasks

### D1. Nested calls vs. one batched request
- **Question:** should a decision tree be sequential decision-model calls (level 0 → 1 → 2), or one request that asks every level's questions at once ("speculative fan-out"), with code walking the tree?
- **Context:**
  - Jev judges all questions in a request in parallel; TypeSafe's cookbook found 13 questions in one request 12.2× cheaper and 10× faster than separately.
  - Choice questions allow up to 255 options. Ollama is much tighter: 64 questions, 26 options.
  - Sequential levels put several round trips on every turn's critical path.
- **Ideas / options:**
  1. One batched request plus code tree-walk as the default.
  2. Nested calls only when a lower level needs a different state (e.g. retrieved docs).
  3. Hybrid.
- **Agent's lean (unverified):** batch by default, nest only when needed. Benchmark both on real traffic.

### D2. Should one decision task allow many questions per call?
- **Context:** Pydantic AI turns every field of an output type into a Jev question answered in one request.
- **Agent's lean (unverified):** yes. A multi-field output schema on a Kiln task could map directly to one multi-question request.

### D3. Keep the decision separate from the action
- **Question:** should a decision-model task's output schema *be* the middleware response schema (including content and overrides)?
- **Context:**
  - Decision models can't write free text: Pydantic AI hands any route with a `str` field to an LLM.
  - TypeSafe's guidance: "classification by model, routing by code."
- **Ideas / options:**
  - Decision tasks output IDs and probabilities (`canned_id`, `model_tier`, `needs_reasoning`).
  - A thin mapping layer (config or code) turns IDs into actions: canned text, override bundles.
  - Canned answer text then becomes versioned config, editable without touching the model.
- **Agent's lean (unverified):** separate them. "Middleware can be any task conforming to the middleware schema" may still work if the schema is IDs and probabilities rather than text.

### D4. Probabilities as a first-class task output
- **Question:** where do confidence and probabilities live in a Kiln task run?
- **Context:**
  - AI SDK hides them in `providerMetadata`; LangChain keeps the full answer in state; Pydantic uses `provider_details`.
  - TypeSafe recommends a separate threshold per action, and warns that probability split between adjacent score levels can pass a confidence check yet land on the wrong side of a threshold.
- **Agent's lean (unverified):**
  - Make probabilities a typed part of the decision-task output.
  - Support a threshold per route.
  - Note that a Noul (boolean) has no separate confidence; the probability is the answer.

### D5. Which decider APIs to support
- **Context:** `/v1/systemone` is the de facto standard (Jev, Strands Decider, Ollama, Upstage). OpenAI's `/v1/decisions` is different.
- **Ideas / options:** systemone first, then an OpenAI Decisions adapter, then an LLM structured-output fallback. Support local deciders for privacy and latency.
- **Agent's lean (unverified):** systemone plus the LLM fallback covers most cases. Add OpenAI if users ask.

---

## E. Optimization loop (possible differentiator)

### E1. Evaluate routing decisions, not just trace them
- **Question:** how far should Kiln go in evaluating and optimizing middleware decisions?
- **Context:**
  - Competitors only trace them (LangSmith, Logfire).
  - Vercel's guide tells users to monitor against a single-model baseline and tune thresholds on labeled data.
  - AWS released Strands Decider's training data and scripts; Together published a $17 train-your-own walkthrough.
- **Ideas / options:**
  - Log each decision with probabilities and the downstream outcome as a dataset row.
  - Evals for "was routing to the cheap model OK?" and "was the canned answer appropriate?"
  - Threshold tuning per route.
  - Synthetic data for decision tasks, then fine-tune a custom decider.
- **Agent's lean (unverified):** this looks like the strongest gap in the market, and it fits Kiln's existing eval / synthetic data / fine-tuning features.

### E2. Cache-aware routing
- **Question:** should the router account for prompt-cache state?
- **Context:**
  - This is agent analysis, not sourced. Cached input typically costs ~10% of the normal input price. Moving a long cached conversation to an uncached cheaper model can cost *more* on input unless that model is more than ~10× cheaper.
  - None of the routing docs reviewed mention this.
  - The spec already lists "better cache reuse."
- **Ideas / options:**
  - Default to sticking with the current model, and switch only on a large confidence gap.
  - Give the router conversation length and current-model cache state as inputs.
  - Route more aggressively at conversation start.
  - Report the realized cost against a "no routing" counterfactual.
- **Agent's lean (unverified):** worth modeling. Check the numbers against current pricing first.

---

## F. Runtime behavior

### F1. Failure policy
- **Question:** what happens when a decider times out or errors?
- **Context:** eve's fallback covers only decider failures. Qoder has no fallback (failures fail the request). Pydantic AI hooks support timeouts.
- **Ideas / options:**
  - A timeout on every middleware.
  - A fail-open / fail-closed setting: fail-open (pass through) by default for routing and canned answers, fail-closed opt-in for guardrails.
  - Retry once on transient errors.
- **Agent's lean (unverified):** fail-open by default, with a timeout on every middleware.

### F2. Latency budget and streaming
- **Question:** how much added time before the first token is acceptable? Should canned answers stream like LLM output?
- **Context:** reported decision-model latencies run ~100–500 ms per request. A stack of middleware adds up.
- **Ideas / options:**
  - Run independent middleware decisions in parallel.
  - Run the decision call speculatively alongside a cheap default LLM call, and cancel whichever loses.
  - Stream canned text so client UX stays consistent.
- **Agent's lean (unverified):** measure first. Parallel batched decisions probably cover most cases.

### F3. LLM as router
- **Question:** should the design treat an LLM router (light reasoning, long cached prompt) as first-class or as rare?
- **Context:** the Vercel guide layers regex heuristics → decision model → threshold. Frameworks mostly assume a decision API.
- **Agent's lean (unverified):** support it, since "middleware = task" makes it free. Document decision models as the default.

---

## G. Implementation choices

### G1. "Code tasks"
- **Question:** should Kiln add code tasks, reusing the code-tools infrastructure, so every middleware is "a task"?
- **Context:** Pydantic AI's `FunctionModel` (a model backed by a Python function) is a precedent for treating code as a model or task.
- **Agent's lean (unverified):** it seems clean, and gives testing and versioning for free. The alternative is code middleware as a separate kind of object.

### G2. Testing
- **Question:** how do users test middleware stacks offline?
- **Context:** OpenAI Agents SDK has `ScriptedModel`; Pydantic AI has `FunctionModel` / test models; the `typesafe-jev` Rust client takes a fake transport.
- **Agent's lean (unverified):** ship a fake or scripted decider with fixed answers and probabilities.

### G3. Build vs. adopt
- **Question:** should Kiln extend its own harness, or adopt an existing framework?
- **Context:** no framework combines canned trees, routing, confidence gating and an eval loop. Adopting LangChain or Pydantic AI means taking on their whole agent loop.
- **Agent's lean (unverified):** extend Kiln. Use LangChain v1 middleware (Python, most mature) and Pydantic AI capabilities/hooks as API references.

### G4. Naming
- **Question:** what to call it?
- **Context:** the industry calls the abstraction "middleware" (LangChain), "capabilities/hooks" (Pydantic AI), "callbacks" (ADK), "processors" (Mastra), "hooks" (Strands).
- **Agent's lean (unverified):** "middleware" is the most widely understood, and matches the HTTP mental model in the rough design.

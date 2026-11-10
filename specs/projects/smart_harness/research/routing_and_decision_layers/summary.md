# Research: Smart Routing and Pre-LLM Decision Layers

Research pack prepared 2026-11-09 by a research agent, supplied by the project owner as input to this spec.

| File | What it is | How to treat it |
|---|---|---|
| [competitive_report.md](competitive_report.md) | What competitors and decision-model vendors ship, and how they do routing, canned answers and middleware. Sourced, with links. | Facts as of 2026-11-09. Most APIs are experimental and change weekly; re-verify before depending on details. |
| [open_design_questions.md](open_design_questions.md) | Open questions and ideas raised during research. | **Unverified and not directional.** A research agent's opinions only. Not requirements or decisions unless the project owner confirms them in the functional spec. |

## Key findings (from the competitive report)

- Decision models ("System One" models) are a new product category. TypeSafe's `POST /v1/systemone` is the emerging standard (Jev, AWS Strands Decider, Upstage, Ollama 0.35+, llama.cpp, vLLM). OpenAI's `/v1/decisions` uses a different schema.
- Jev judges all questions in one request in parallel and bills the state once. Batching 13 questions measured 12.2× cheaper and 10× faster than one at a time. Latency is roughly 100–500 ms per request.
- The middleware/hook shape has converged across LangChain v1, Pydantic AI and Google ADK: skip the model and return a result, override settings, pass through, and stack in a documented order (before-hooks in order, wrap-hooks nested with the first outermost, after-hooks reversed). Shared state lets later hooks read earlier decisions.
- Most frameworks separate hook levels: per run / user turn, per model call, per tool call.
- Provider constraint, **claimed by the report and under test**: with Anthropic extended thinking, an assistant tool call written by the harness (no thinking block) causes a 400, and thinking config should stay fixed within one assistant turn (a tool loop is one turn). LiteLLM is said to silently drop `thinking` for that turn instead. See [../harness_tool_call_probe/](../harness_tool_call_probe/) for the check against live providers and current docs.
- Gaps no competitor fills: confidence-gated escalation, declarative canned-response trees, a combined pipeline (deterministic → canned → model/thinking selection → escalation), and evaluating/optimizing routing decisions rather than only tracing them.

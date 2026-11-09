# Competitive Report: Smart Routing and Pre-LLM Decision Layers

**Prepared:** 2026-11-09, for the Kiln Smart Harness spec
**Scope:** how agent frameworks and decision models handle (a) choosing the model and thinking level for each turn, and (b) answering without an LLM (canned answers, decision trees, injected actions).
**Caveat:** almost everything below is experimental, under eight weeks old, and changing every week. Re-check the docs before relying on any API detail. Each section names its source, and all links are at the end.

---

## TL;DR

- **Decision models became a product category in about eight weeks.** TypeSafe's Jev launched 2026-09-15. OpenAI, AWS, Microsoft, Cloudflare, Perplexity, Upstage, Liquid, Snowflake and a dozen open-source projects shipped their own versions within a month.
- **One API shape is becoming the standard: TypeSafe's `POST /v1/systemone`.** AWS Strands Decider, Upstage, Ollama 0.35+, llama.cpp and vLLM all serve it. OpenAI does not (it uses its own `/v1/decisions`).
- **Model routing:** only two frameworks have it as a configuration option.
  - Vercel **eve** `auto`: re-decides each user turn, Jev by default, and each option can set a reasoning level.
  - LangChain **`ModelRouterMiddleware`**: alpha, decides once per run.
  - Everyone else provides hooks and you build it yourself.
- **Canned answers / decision tree with an LLM fallback:** only **Pydantic AI** comes close. You make a decision model the agent's model, and `ModelFallback` hands any step it can't fill to an LLM. No framework ships declarative canned-response trees.
- **Nobody combines the pieces.** There's no single feature that goes "deterministic or canned answer → pick model and thinking level → escalate when unsure."
- **Nobody treats routing decisions as something to evaluate and optimize.** Frameworks trace decisions (LangSmith, Logfire); none closes the loop. Vercel's routing guide tells you to tune thresholds against a labeled eval set, but leaves that to you.
- **The middleware/hook shape has converged** (LangChain v1 middleware, Pydantic AI capabilities, Google ADK callbacks): skip the model, override settings, pass through, and stack in order (wrap hooks nest, after-hooks run in reverse).

---

## 1. Decision models ("System One" models)

### 1.1 Jev (TypeSafe AI): the reference implementation

- **Launch:** 2026-09-15, when TypeSafe came out of stealth; reported $40M seed led by DCVC. Founder Diogo Almeida (ex-OpenAI, InstructGPT/RLHF). A later valuation of $7.5B has been reported (DoNews; unverified).
- **What it is:** a model that doesn't generate text. It takes a *state* (string, JSON or messages) plus named, typed *questions*, and returns typed answers with probabilities.
  - Question types: **Choice**, **Score**, **Noul** (boolean probability), and **Box** (image regions, Jev 1.14+ only).
  - TypeSafe calls it a "System One model", after Kahneman's fast/slow thinking. The name Jev comes from economist William Stanley Jevons.
- **Pricing:** $0.042 per million input tokens. Output is free.
- **Latency:**
  - TypeSafe reports 70–500 ms.
  - An independent support-ticket test measured a ~0.4 s median.
  - OrcaRouter measured daily medians of ~143–175 ms over a week.
- **Limits (jev-1.13):**
  - 64K tokens per request in total, and 32K for the state plus the longest question.
  - Up to 255 options per Choice question.
  - Published rate limits of 1,200 requests/min and 250K tokens/s, flagged as "adjusting". Other sources quote different figures, so verify.
- **Versions:** `jev-1.13.0` (= `jev-latest`). `jev-1.14.0` (= `jev-preview`, released 2026-10-14) improves multilingual answers, adds experimental image input, and per press reports isn't recommended for production.
- **Asking many questions at once ("speculative fan-out"):**
  - All questions in one request are judged in parallel against the same state, and the state is billed once.
  - TypeSafe's cookbook measured 13 questions in one request at 12.2× cheaper and 10× faster than asking them one at a time, with the same answers.
  - TypeSafe's advice is to ask the questions you *might* need and let code choose which answers to use.
- **TypeSafe's own positioning:** "classification by model, routing by code."
  - It recommends hard policy in code first, then the decision model, then deterministic code / specialist LLMs / human review.
  - It frames Jev as a component of AI-powered software, not as the agent itself.
- **Known weaknesses:**
  - It can't do arithmetic, counting, date comparisons or indirect reasoning, and isn't built to resist adversarial input.
  - Early reports call production calibration unproven.
  - Some developers (e.g. Sean Goedecke) argue it's essentially an LLM with structured output, and that the interface is the real value.
- **Adoption signal:** on Vercel AI Gateway, Jev reached ~13% of paid teams within 24 h and ~35% within two weeks, Vercel's fastest-adopted model ever. Gateway access was free until 2026-09-25, which inflates the early numbers.

### 1.2 Competitors and clones

| Model / API | Vendor | Hosted or open | Notes |
|---|---|---|---|
| Decisions API (`/v1/decisions`) | OpenAI | Hosted | GPT-6 Luna. Predicate / choice / score questions. $0.10/M input, no output or cache charges. Public beta 2026-10-06; later GA with prompt caching and up to 400 questions per request. **Different schema from `/v1/systemone`.** |
| Strands Decider 2B | AWS (Strands Labs) | Open (Apache 2.0) | Qwen3.5-2B with the text head replaced by a ~1M-param pointer head that scores options. ~115 ms median on an RTX 3090. 72.3% on JevBench public. Training data and scripts released. Serves `/v1/systemone`. An experiment, not a managed AWS service. |
| Microsoft-Decision-1 | Microsoft | Hosted (Foundry, OpenRouter) | Post-trained from Qwen3.5-9B. ~$0.042/M reported. Microsoft says it will later rebase on Microsoft (MAI) and OpenAI models. |
| pplx-decider | Perplexity | Open (27B) and hosted | ~$0.02/M hosted. |
| Solar Decide | Upstage | Hosted | Built on Solar Mini 4. Served through the `/v1/systemone` schema. |
| Clef | Cloudflare | Hosted | |
| d1 | Liquid AI | Hosted / OpenRouter | `/v1/systemone`-compatible. |
| Snowflake Decision | Snowflake | Hosted | |
| Tev1 (4B / 0.8B) | Together AI | Open | Published with a "train your own decision model for $17" walkthrough. |
| Nimble | Bespoke Labs | Open (Ollama) | |
| CLM-8B | Stanford / NVIDIA | Open | Reported to be 9× faster than Jev. |
| OpenJev, NanoJev, Laya, Kev, WaterSheep, Von, Standard One, Intern-Decision… | Various | Open | Long tail of open projects. |

**Runtimes:**
- Ollama 0.35+ serves `/v1/systemone`. Limits noted in docs: max 64 questions, 26 options per question, 64 KiB per request.
- llama.cpp and vLLM have `systemone` endpoints.
- Ollaya bundles several open decision models behind one endpoint.

**Benchmark:** JevBench, an independent benchmark that the competitors quote.

**The schema standard:** AWS, Upstage and Ollama all converged on TypeSafe's `/v1/systemone`; OpenAI hasn't signed on. Simon Willison said he would have preferred a standard based on Chat Completions.

---

## 2. Framework-by-framework

Legend: **Native** = configure and go. **Hooks** = you write the logic in a hook or middleware. **Absent** = nothing found.

| Framework | Per-turn/step model routing | Thinking level per turn/step | Decision-model integration | Skip LLM / canned answer | Guide doc for the pattern |
|---|---|---|---|---|---|
| Vercel eve | **Native** (`auto`, per user turn) | **Native** (per option) | **Native** (Jev default) | Absent | Yes (eve "Automatic Model Selection") |
| Vercel AI SDK v7 | Hooks (`prepareStep`, per step) | Hooks (`reasoning` in `prepareStep`) | `experimental_decide` (standalone) | Absent natively | Yes (Vercel KB cost-aware routing) |
| LangChain v1 | **Native-ish** (`ModelRouterMiddleware`, alpha, once per run) + hooks | Hooks only | `langchain-typesafe` (alpha) | Hooks (`jump_to: end`, return early) | Yes (TypeSafe integration page) |
| Pydantic AI v2 | Hooks (`SelectModel`, per step) | Hooks / `Thinking` capability | **Native** (`DecisionModel`, `SystemOneModel`) | **Native-ish** (decision model as agent + `ModelFallback`; `SkipModelRequest`) | Yes (support-desk worked example) |
| Google ADK | Hooks (`RoutedLlm`, TS only, experimental) | Hooks (mutable `LlmRequest`) | Absent | **Native hook** (callback returns a response) | Partial (callbacks docs) |
| Mastra | Hooks (`processInputStep`) | Hooks | Classifier support (processors, scorers, tool approval) | Hooks (abort) | Partial (Mastra Jev article) |
| OpenAI Agents SDK | Per agent / per run only | Per agent | Absent (even for OpenAI's own Decisions API) | Guardrail tripwires | No |
| AWS Strands | Hooks exist; no documented model swap | Unclear | Strands Decider (separate project); "integration libraries" promised | Unclear | No |

### 2.1 Vercel AI SDK (v7)

- **`prepareStep`** (renamed from `experimental_prepareStep` in v7):
  - Can change `model`, `toolChoice`, `activeTools`, `messages` and call settings for each step, including `reasoning`. Overrides apply to that step only.
  - v7 change: returned instructions and messages now carry forward into later steps.
- **Decisions API in core:**
  - `experimental_decide` takes one shared state and answers several named questions: choice, score, boolean, box.
  - Provider-specific confidence comes back in `providerMetadata` (e.g. `typesafe.confidence`).
  - Earlier changelogs and the eve docs used `experimental_evaluate` / `evaluationModel`, so the name appears to have changed. Verify.
- **How to reach Jev:** the `typesafe-ai/jev` model string via AI Gateway, or the `@ai-sdk/typesafe-ai` package directly (Jev support starts in AI SDK 7.0.105).
- **What the docs don't cover:**
  - Using decisions inside `ToolLoopAgent`, inside `prepareStep`, or to skip the model with canned responses.
  - Routing is shown only as application code that branches on the answer after the call.
  - Core doesn't switch models on its own; AI Gateway supports conditional decision fallbacks via `providerOptions.gateway.models`.
- **Skipping the LLM:** `prepareStep` can't skip the model call. The documented alternatives are `stopWhen`, a tool without `execute`, or a manual loop. (From general knowledge, not verified here: language-model middleware via `wrapLanguageModel` can return a result without calling the provider.)
- **Guide, "Cost-aware model routing with Vercel AI Gateway":** the best end-to-end process doc found. It layers checks, cheapest first:
  1. Regex heuristics (code blocks, "debug", "prove", "refactor") send requests straight to the frontier tier. Request length is deliberately not used.
  2. Undecided requests go to a decision model (Jev, or OpenAI Decisions as the default) choosing between written profiles of each tier.
  3. A threshold: the fast tier is used only if its probability is ≥ 0.85 (an example value).
  4. An escalation path for tasks with verifiable outputs: start on the fast model, escalate on a failed check.
  5. Separate budgets per tier, enforced with separate API keys.
  6. Monitoring against a single-model baseline, and tuning against a labeled eval set.
  
  Not covered: reasoning effort, canned answers.
- **Related, Cloudflare Agents "Think" (built on AI SDK):** `beforeTurn` (override model, tools or prompt for the whole turn) and `beforeStep` (passed through to `prepareStep`). This is a clear example of separating turn-level from step-level hooks.

### 2.2 Vercel eve

- Open-source TypeScript agent framework, announced 2026-06-17 at Vercel Ship. An agent is a directory of files and runs on Vercel's durable Workflows.
- **`auto` from `eve/models`:**
  - Picks the agent's model from an allowlist of `{ key: description }` options, using the AI SDK decisions API. The default decider is `typesafe-ai/jev`.
  - **When:** once per user turn, at the first `step.started`. The choice is reused for the tool-loop steps in that turn.
  - **Thinking level per option:** `provider-default | none | minimal | low | medium | high | xhigh`. If omitted, it inherits the agent's setting.
  - **Failure handling:** `fallback` applies only when the decider fails or errors. There's no confidence threshold.
  - **What the decider sees:** option keys and descriptions, plus up to 8 recent user/assistant text messages, capped at 16K characters. It never sees credentials.
- **Other Jev uses in eve:**
  - `approval: auto(...)` lets Jev approve tool calls.
  - "Route to a hidden subagent with Jev": the specialist is hidden from the parent model, and the Jev call runs in a `"use step"` helper so replays reuse the recorded decision.

### 2.3 LangChain v1 (Python / JS)

- **Middleware hooks:** `before_agent` / `after_agent` (once per run), `before_model` / `after_model` (each model call), `wrap_model_call`, `wrap_tool_call`.
  - **Order:** before-hooks run in list order, wrap-hooks nest like function calls, after-hooks run in reverse.
  - **Skipping ahead:** node-style hooks can return `jump_to` (`end`, `tools`, `model`), declared with `can_jump_to`.
  - **Wrap hooks:** call `handler(request)` to proceed, or return early to skip the model.
  - **Overrides:** `request.override(model=..., system_message=..., tools=...)`.
  - Custom state schemas let middleware share state with each other.
- **`langchain-typesafe` (alpha, `[experimental]` extra):**
  - **`ModelRouterMiddleware`:**
    - Hooks `before_agent` and `wrap_model_call`. Configured as `choices={name: ModelChoice(model, criteria)}` plus router `instructions`.
    - Classifies the **latest human message once per agent run**. The full answer, with probabilities and confidence, goes into the state at `model_route`, and every model call in the run uses that pick.
    - Not documented: a low-confidence fallback or threshold, reasoning-effort control, or skipping the LLM.
  - **`AutoModeMiddleware`:** classifies calls to configured tools and blocks risky ones before they run.
  - **`TypeSafeClassifier`:** a Runnable for direct calls. Decisions are traced in LangSmith.
- **Built-in middleware worth knowing:** `ModelFallbackMiddleware`, `ModelRetryMiddleware`, `ModelCallLimitMiddleware`, `SummarizationMiddleware`, `ContextEditingMiddleware`, tool retry and tool selection.
- **Community, `langchain-router`:** routes by agent phase with no ML at all:
  - user spoke → primary model
  - tool call succeeded → fast model
  - tool call failed → primary model
- **Commentary worth noting (Medium, "Harness Engineering"):** suggests re-routing only at safe boundaries, i.e. between user turns and never mid tool loop.

### 2.4 Pydantic AI (v2)

- **Capabilities:**
  - Bundles of tools, hooks, instructions and model settings, attached with `capabilities=[...]`. They can also be loaded from a YAML/spec file.
  - Hook levels: run, node, model request, tool validation and tool execution.
  - Order: before-hooks in order, after-hooks reversed, wrap-hooks nest with the first one outermost. Hooks can take a `timeout`.
- **Swapping the model:** set `request_context.model` in `before_model_request` or the wrap hook.
- **Skipping the LLM:** raise `SkipModelRequest(response)`. This is done with an exception.
- **`SelectModel` capability:** a callable run before each new logical model request. It can read dependencies, prompt, history, usage, step, deadlines and output-retry counts.
- **Decision models:**
  - `DecisionModel` base class, with `TypeSafeModel` (`typesafe:jev-latest`) and `SystemOneModel` (any `/v1/systemone` server, e.g. Ollama or Strands Decider) on top. You switch backends by changing the model.
  - An agent running on a decision model turns its output types into Jev questions. It can also pick tools and fill their arguments when the argument types are ones Jev can answer.
- **Escalation to an LLM (`ModelFallback`):**
  - Picking a route Jev can't fill (e.g. one with a `body: str` field) raises `UnfillableRoute`.
  - A low-confidence pick, when `decision_route_threshold` is set, raises `UnsureRoute`.
  - Both are `DecisionHandOff` errors, and `ModelFallback(fallback_on=DecisionHandOff)` hands the whole step, with the same tools and output types, to the LLM. Earlier steps stay on Jev.
- **Worked example ("A support desk, end to end"):** output types `Triage`, `Refund`, `Reply` plus a `check_status` tool. Two of three sample tickets resolve with no LLM; "Is login down?" escalates once for the `Reply` step.
- **Cost warning in Pydantic's docs:** if most requests get handed off, you pay for a decision call *plus* an LLM call, which can be slower than not using a decision model. Measure the hand-off rate first.
- **Also relevant:**
  - `FunctionModel`, a model backed by a Python function (a precedent for "code tasks").
  - Logfire Live view shows each question, answer and probability.
  - The `jevantic` alpha adds guardrails, and an Apache Airflow provider exposes decision models through Pydantic AI.

### 2.5 Google ADK

- **Callbacks:** `before_agent` / `after_agent`, `before_model` / `after_model`, `before_tool` / `after_tool`. Every before-callback either returns `None` to proceed or returns an object to **skip** that step.
  - `before_agent_callback` returning `Content` skips the whole agent invocation.
  - `before_model_callback` returning an `LlmResponse` skips the LLM; the response is treated as if the model produced it. The docs' examples include serving from cache and **forcing a function call instead of an LLM call**.
  - `LlmRequest` can be edited in place, and the callback parameters accept lists.
- **`RoutedLlm`** (ADK TypeScript v1.0.0, experimental):
  - A `router(models, llmRequest, errorContext)` function picks a model key for each request. It's re-called with error context if the chosen model fails before producing output.
  - Live connections pick once, at connect time.
  - `RoutedAgent` is the variant for also switching instructions, tools or sub-agents.
  - The docs don't mention thinking config, and list "auto-routing by input complexity" as a use case without explaining how.
- **Not found:** a Python equivalent of `RoutedLlm`, or any first-party decision-model integration.

### 2.6 Mastra (TypeScript)

- **Processors:** `processInput` (once), `processInputStep` (every step, including after tool calls; used for per-step model or tool-choice switching), `processLLMRequest`, `processOutputStream`, `processLLMResponse`, `processOutputStep`. `prepareStep` is also accepted on `generate` / `stream`.
- **Classifier support** for Jev and compatible models: `ClassifierProcessor` for guardrails (can call `abort()`), `createClassifierScorer` for evals, and tool-approval checks. `errorStrategy: 'warn'` lets the agent continue if a classifier fails.
- **Mastra's own finding:** Jev fits some classification problems but not all. Issue triage, for example, needs context Jev doesn't have.

### 2.7 OpenAI Agents SDK

- **Model selection:** set per agent or per run, with precedence `RunConfig.model` > `Agent.model` > SDK default. `callModelInputFilter` can change instructions and input before a call, but not the model.
- **Routing:** handoffs to specialist agents, or decide before `Runner.run`. There are input/output guardrails.
- **Not found:** any integration with OpenAI's own Decisions API. This is the weakest fit for per-turn model routing.

### 2.8 AWS Strands Agents

- **Hooks:** `BeforeInvocationEvent`, `BeforeModelCallEvent`, `AfterModelCallEvent`, `BeforeToolCallEvent`, `AfterToolCallEvent`, `MessageAddedEvent`, etc. Most event properties are read-only; a few (e.g. `retry`, `cancel`) can be changed. No documented way to swap the model was found.
- **Decider:** Strands Decider 2B is a separate Strands Labs project. AWS says it's working on decision-model integration libraries.

### 2.9 Others worth knowing

- **Qoder Agent SDK, `resolve_model`:** a callback run before *every* LLM request that returns a model plus parameters (`contextWindow`, `reasoningEffort`). It can route by purpose (main / subagent / compaction). There's **no automatic fallback**: a timeout or exception fails the request. This is the closest existing API shape to "model + thinking level for each call".
- **OpenRouter `callModel`:** `model` can be a function of context (e.g. `numberOfTurns`).
- **Gateways and routers:** Vercel AI Gateway, OpenRouter, ZenMux (lists Jev but doesn't say Jev drives `zenmux/auto`), Azure AI Foundry Model Router, NeMo Switchyard (per-turn routing for coding agents; not researched).

---

## 3. The converged middleware pattern

| Behavior | LangChain v1 | Pydantic AI | Google ADK | Mastra |
|---|---|---|---|---|
| Skip the LLM, return a result | Return early from `wrap_model_call`; or `jump_to: "end"` with messages | `raise SkipModelRequest(response)` | `before_model_callback` returns `LlmResponse` (may contain a function call) | `abort()` from a processor |
| Override model / settings | `handler(request.override(model=...))` | Set `request_context.model` / settings | Edit `LlmRequest` in place | Return overrides from `processInputStep` |
| Do nothing | Return `None` / `handler(request)` | Return the context unchanged | Return `None` | Return input unchanged |
| Stacking | List; before in order, wrap nested, after reversed | Capability list; same ordering | Lists of callbacks | Processor arrays |
| Shared state between middleware | Custom state schema | Run context / deps | `callback_context.state` | `RequestContext` |
| Hook levels | Agent run, model call, tool call | Run, node, model request, tool | Agent, model, tool | Input (once), step, LLM request/response, output |

What the frameworks share:
- **Wrap hooks** (`handler` / `next`) are the most expressive form. They can short-circuit, override, and post-process.
- **Node-style before/after hooks** are offered alongside as a convenience.
- **Order is explicit and documented.**

AI SDK `prepareStep` and eve `auto` are single callbacks or config, not stackable middleware.

---

## 4. Provider constraints that affect routing design

- **Anthropic extended thinking:**
  - **Keep one thinking configuration per assistant turn.** A tool-use loop is one assistant turn, so change the thinking configuration only between turns.
  - Thinking blocks must be passed back complete and unmodified. When thinking is on, the final assistant message must start with a thinking block (before the last set of `tool_use` / `tool_result` blocks). Otherwise the API returns a 400.
  - **This means a fabricated assistant tool call, inserted by the harness without a thinking block, breaks thinking-enabled requests.**
  - Forced `tool_choice` (`any` / a specific tool) isn't compatible with manual extended thinking.
- **LiteLLM:** if an assistant message with `tool_calls` lacks `thinking_blocks`, LiteLLM **silently drops the `thinking` parameter for that turn** to avoid the error.
- **Routing cost and caching:** none of the routing guides or frameworks reviewed mention how switching models interacts with prompt caching.

---

## 5. Guides and reference docs available

| Doc | Covers | Doesn't cover |
|---|---|---|
| Vercel KB: Cost-aware model routing with AI Gateway | Full routing process: heuristics → decision model → threshold → escalation on failed checks → budgets → evaluation and tuning | Thinking level, canned answers, agent loops |
| eve docs: Automatic Model Selection | Per-turn model + reasoning routing with Jev | Confidence thresholds |
| LangChain: TypeSafe integration page | `ModelRouterMiddleware` / `AutoModeMiddleware`, complete `create_agent` example | Low-confidence handling |
| LangChain: custom middleware | Hook types, ordering, `jump_to`, `request.override` | Decision models |
| Pydantic AI: Decision models | Routes as output types, `ModelFallback` hand-off, thresholds, support-desk worked example | Canned text responses |
| Pydantic AI: Hooks / Capabilities / SelectModel | Model swap, `SkipModelRequest`, ordering, timeouts | |
| TypeSafe: Routing by probability (intent routing) | Per-action thresholds; riskier actions need higher probability; low confidence → clarify or human | Model routing |
| TypeSafe: Routing by confidence | Gate on confidence before score; fix for probability split between adjacent levels | Model routing |
| Wavect: Jev review | Routes `deterministic_code` / `fast_llm` / `reasoning_llm` / `human_review` with a confidence threshold per route; hard policy in code first | Framework integration (blog, not a framework) |
| TDS: Cheap, reliable model router with Jev | Worked router with a low-confidence fallback tier | |
| ADK callbacks docs | Short-circuit semantics, forcing function calls | Model routing |

---

## 6. Gaps in the market (as of 2026-11-09)

1. **Confidence-gated model escalation:** eve falls back only on errors, and LangChain stores the confidence but doesn't act on it. Pydantic AI has a threshold, but it only covers handing off from the decision model to the LLM.
2. **Declarative canned-response trees:** none found.
3. **A combined pipeline** (deterministic → canned → model/thinking selection → escalation): none found.
4. **Thinking level as a routing choice:** only eve (per option) and AI SDK `prepareStep` (per step).
5. **Evaluating and optimizing routing decisions:** only tracing exists (LangSmith, Logfire). Vercel's guide recommends tuning thresholds on labeled data, but doesn't provide the tooling.
6. **Cache-aware routing:** no mention found.
7. **Training your own decider:** possible with AWS's open data and scripts and Together's walkthrough, but not built into any framework.

---

## Sources

**Decision models**
- Arize — TypeSafe's Jev: https://arize.com/blog/typesafe-jev-llm-judge/
- Wavect — Jev review: https://wavect.io/blog/jev-ai-decision-model-review/
- Towards AI — Jev overview: https://pub.towardsai.net/jev-ai-just-killed-the-most-wasteful-habit-in-software-and-nobodys-talking-about-it-576706112df6
- Jev limits: https://opentweet.io/jev/limits
- Jev limitations: https://www.orcarouter.ai/blog/jev-limitations
- Jev fan-out vs one-at-a-time: https://pub.towardsai.net/asking-jev-13-questions-one-call-at-a-time-caps-you-at-92-docs-a-minute-one-request-gets-1-200-cc7becabfdb1
- Jev 1.14 (DataLearner): https://www.datalearner.com/ai-models/pretrained-models/1199
- Jev architectural patterns (Linyb): https://www.besthub.dev/articles/jev-decision-model-extracting-structured-judgments-from-llms-for-code-driven-routing-044d92bc4bf4
- TypeSafe — Routing by probability: https://docs.typesafe.ai/patterns/intent-routing
- TypeSafe — Routing by confidence: https://docs.typesafe.ai/patterns/confidence-routing.md
- The New Stack — decision-model API convergence: https://thenewstack.io/?p=22839528
- The New Stack — Strands Decider: https://thenewstack.io/aws-strands-decider-model/
- Techstrong — Strands Decider: https://techstrong.ai/articles/aws-explores-decision-models-with-strands-decider-2b/
- OpenAI Decisions API (Let's Data Science): https://letsdatascience.com/news/openai-opens-decisions-api-public-beta-b69a1e40
- OpenAI Decisions API GA (TechEnclave): https://techenclave.com/news/items/openai-opens-decisions-api-priced-at-0-10-per-million-input-tokens
- Microsoft-Decision-1: https://www.producthunt.com/products/microsoft-decision-1
- Decision-model landscape (Kai Waehner): https://www.kai-waehner.de/?p=11093
- awesome-decision-models: https://github.com/AnotiaWang/awesome-decision-models/wiki
- TechCrunch — Jev adoption on Vercel: https://techcrunch.com/?p=3178711
- Vercel adoption figures (MacMyths): https://macmyths.com/jev-is-vercels-fastest-adopted-ai-model-ever/
- Stack Archive — System One API vs OpenAI: https://stack-archive.com/blog/decision-model-api-system-one-standard-aws-ollama-2026/

**Vercel**
- AI SDK loop control: https://ai-sdk.dev/docs/agents/loop-control
- AI SDK decisions: https://ai-sdk.dev/docs/ai-sdk-core/decisions
- AI SDK TypeSafe provider: https://ai-sdk.dev/providers/ai-sdk-providers/typesafe-ai.md
- AI SDK v6 → v7 migration: https://mcpservers.org/hi/agent-skills/vercel/ai/migrate-ai-sdk-v6-to-v7
- Cost-aware routing guide: https://vercel.com/kb/guide/cost-aware-model-routing-with-ai-gateway
- eve Automatic Model Selection: https://cdn.jsdelivr.net/npm/eve@0.77.0/docs/guides/decide.md
- Jev in an agent loop (Vercel): https://vercel.com/i/jev-agent-control
- AI Gateway Jev changelog: https://vercel.com/changelog/ai-gateway-now-supports-typesafe-clients-and-an-http-api-for-jev
- Cloudflare Think lifecycle hooks: https://developers.cloudflare.com/agents/think/lifecycle-hooks/

**LangChain**
- TypeSafe integration: https://docs.langchain.com/oss/python/integrations/providers/typesafe
- langchain-typesafe on PyPI: https://pypi.org/project/langchain-typesafe/
- Custom middleware: https://docs.langchain.com/oss/python/langchain/middleware/custom
- langchain-router: https://pypi.org/project/langchain-router/
- Harness Engineering article: https://levelup.gitconnected.com/harness-engineering-ai-agent-gate-and-model-router-the-system-one-jev-model-langchain-c6f80e79f8be

**Pydantic AI**
- Decision models: https://pydantic.dev/docs/ai/models/decision/
- System One API: https://pydantic.dev/docs/ai/models/system-one/
- TypeSafe model: https://pydantic.dev/docs/ai/models/typesafe/index.md
- Select Model: https://pydantic.dev/docs/ai/capabilities/select-model/
- Hooks: https://pydantic.dev/docs/ai/core-concepts/hooks/
- Capabilities migration (DEV): https://dev.to/deenuu1/pydantic-ai-capabilities-hooks-agent-specs-what-changed-and-how-our-libraries-migrated-4i18
- Airflow decision models: https://airflow.apache.org/docs/apache-airflow-providers-common-ai/stable/decision_models.html

**Google ADK**
- Model routing: https://adk.dev/agents/models/routing/
- Callbacks (Google Cloud): https://docs.cloud.google.com/gemini-enterprise-cx/cx-agent-studio/callback
- Callbacks explainer: https://ravichaganti.com/blog/google-adk-callbacks/

**Others**
- Mastra processors: https://mastra.nodejs.cn/docs/agents/processors
- Mastra on Jev: https://mastra.ai/articles/jev
- Strands hooks: https://strandsagents.com/docs/user-guide/sdk/agents/hooks-events/
- OpenAI Agents SDK model config: https://agent-foundry-theta.vercel.app/roadmaps/openai-agents-sdk/model-configuration
- Qoder model policy: https://docs.qoder.com/en/cli/sdk/model-policy
- OpenRouter dynamic parameters: https://openrouter.ai/docs/sdks/call-model/dynamic-parameters

**Provider constraints**
- Anthropic thinking + tool workflows: https://platform.claude.com/docs/en/build-with-claude/thinking-tool-workflows.md
- Anthropic extended thinking: https://docs.claude.com/en/docs/build-with-claude/extended-thinking
- LiteLLM reasoning content: https://docs.litellm.ai/docs/reasoning_content

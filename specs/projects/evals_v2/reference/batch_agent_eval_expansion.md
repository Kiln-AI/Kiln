> SUPERSEDED 2026-06-03 — J.37/J.38 content consolidated into design/22_type_deterministic_basics.md.

---
status: draft
---

# Batch J — Agent Eval Expansion (Detail Doc)

**Status:** ✅ **LOCKED 2026-06-02** in Batch J → ALIGNMENT.md §J.37, §J.38. Shapes below updated to the locked form (differ from the original 2026-05-22 proposal — see "Changes at lock time" under each proposal). Archive this doc once `design/22_type_deterministic_basics.md` is authored in Stage 4.

**Purpose:** Capture two proposed agent-eval coverage expansions for later alignment lock. These emerged from the 2026-05-22 critical competitive scorecard pass (`competitive_synthesis.md` §4 + §8, plus a fresh agent-eval gap-analysis sub-agent dispatched 2026-05-22).

**Background:** [ALIGNMENT.md A2.4](ALIGNMENT.md) locks the V2.0 EvalConfigType catalog at 7 types: `llm_judge`, `exact_match`, `pattern_match`, `set_check`, `tool_call_check`, `contains`, and `code_eval` (gated on Batch B, now locked per B.12/B.13). Agent eval is currently served by a single type — `tool_call_check` — which only covers 1 of 4 industry-recognized agent-eval categories.

**Competitive position today (un-expanded):** Promptfoo ships 5 trajectory assertion types covering all 4 categories; DeepEval ships 6 agent metrics. Kiln V2.0 as currently locked = 1 type = competitive loss within the first hour of agent-eval use. Verdict from gap analysis: "If we do nothing, we lose to Promptfoo because they ship 5 config-driven trajectory assertions out of the box and we ship 1."

**Agent-eval categories (industry-standard):**
1. **Trajectory** — did the agent call tool X? in order Y? with args Z?
2. **Outcome** — did the agent achieve the stated goal?
3. **Efficiency** — step count, redundancy
4. **Tool-correctness** — did the agent pick the right tool?

| Category | Promptfoo | DeepEval | Kiln V2.0 today | Kiln V2.0 with both proposals |
|---|---|---|---|---|
| Trajectory | 3 types (`tool-used`, `tool-sequence`, `tool-args-match`) | 2 metrics (Tool Correctness, Argument Correctness) | `tool_call_check` (existence + arg-matching only) | `tool_call_check` (expanded properties — covers all 3 Promptfoo modes in one type) |
| Outcome | `goal-success` (LLM judge) | Task Completion, Plan Adherence | `llm_judge` + ad-hoc prompt | `llm_judge` + first-party "goal achievement" builder template (no new code) |
| Efficiency | `step-count` (min/max bounds) | Step Efficiency | none | `step_count_check` (new type) |
| Tool-correctness | overlaps with trajectory | Tool Correctness | overlaps via `tool_call_check` | overlaps via `tool_call_check` |

The two proposals below are **independent additions** (not alternatives). Either can ship on its own; both together close the gap fully.

---

## Proposal 37 — Extend `tool_call_check.properties`

**Stage 5 schema work only. No new type. Re-amends A2.4 properties contract for the already-locked `tool_call_check` type.**

### Locked Pydantic shape (J.37)

```python
class ArgMatch(BaseModel):
    value: JsonValue
    match_mode: Literal["exact", "contains", "regex"] = "exact"

class ToolCallSpec(BaseModel):
    tool_name: str
    expected_args: dict[str, ArgMatch] | None = None  # None = ignore args

class ToolCallCheckProperties(BaseModel):
    type: Literal["tool_call_check"] = "tool_call_check"
    expected_tools: list[ToolCallSpec]
    match_mode: Literal["any", "all", "ordered", "never"] = "all"
    on_unexpected_tools: Literal["ignore", "fail"] = "ignore"
```

**Changes at lock time (vs 2026-05-22 proposal):**
- **`arg_match_mode` moved from top level to per-arg** (`ArgMatch.match_mode`). Top-level was too wide — one mode across every arg of every tool. Per-arg lets a single call mix `contains` on `query` with `exact` on `user_id`.
- **Added `match_mode="never"`** — forbidden-tool / blocklist check.
- Scalar-shorthand union for `expected_args` (`JsonValue | ArgMatch`) deferred to Stage 5 `design/22` (ergonomics nicety; locked shape above is canonical).

### Semantics

- **`match_mode="any"`** — at least one expected tool was called (subset match)
- **`match_mode="all"`** (default) — every expected tool was called at least once, in any order
- **`match_mode="ordered"`** — expected tools called in the listed sequence (other calls between them are OK unless `on_unexpected_tools="fail"`)
- **`match_mode="never"`** — fail if any of `expected_tools` was called (respecting `expected_args` if set). Under this mode `expected_tools` reads as "forbidden tools".
- **per-arg `match_mode`** (`ArgMatch.match_mode`) — `exact` value equality, `contains` substring on string args, `regex` pattern match
- **`on_unexpected_tools="fail"`** — strict mode; any tool call not in `expected_tools` fails the check

### Use cases this covers

```yaml
# "Agent must call search_web at least once"
expected_tools: [{tool_name: search_web}]
match_mode: any

# "Agent must call search_web THEN fetch_page in order"
expected_tools:
  - {tool_name: search_web}
  - {tool_name: fetch_page}
match_mode: ordered

# "Agent must call search_web with query containing 'Kiln'"
expected_tools:
  - tool_name: search_web
    expected_args:
      query: {value: "Kiln", match_mode: contains}

# "Agent must call ONLY search_web (no other tools allowed)"
expected_tools: [{tool_name: search_web}]
match_mode: all
on_unexpected_tools: fail

# "Agent must NEVER call delete_database"
expected_tools: [{tool_name: delete_database}]
match_mode: never
```

Covers Promptfoo's `trajectory:tool-used`, `trajectory:tool-sequence`, `trajectory:tool-args-match` (3 of 5 trajectory assertion types) plus a forbidden-tool check Promptfoo lacks, in one well-designed properties schema.

### Cost

Zero new type. Stage 5 design work only (properties schema in `design/22_type_deterministic_basics.md`). Implementation likely <150 LOC in Phase 1 (existence check + ordering check + arg matcher).

### Lock target

ALIGNMENT.md A2.4 annotation: "`tool_call_check.properties` shape includes `expected_tools`, `match_mode` (any / all / ordered), `arg_match_mode` (exact / contains / regex), `on_unexpected_tools` (ignore / fail). Full Pydantic shape locked in `design/22_type_deterministic_basics.md`." No catalog change.

---

## Proposal 38 — New `step_count_check` EvalConfigType

**A2.4 catalog expansion. New EvalConfigType added to V2.0 must-ship list.**

### Locked Pydantic shape (J.38)

```python
class StepCountCheckProperties(BaseModel):
    type: Literal["step_count_check"] = "step_count_check"
    count_type: Literal["tool_calls", "model_responses", "turns"]
    min_count: int | None = None
    max_count: int | None = None

    @model_validator(mode="after")
    def check_bounds(self):
        if self.min_count is None and self.max_count is None:
            raise ValueError("step_count_check requires at least one of min_count / max_count")
        if (self.min_count is not None and self.max_count is not None
                and self.min_count > self.max_count):
            raise ValueError("min_count must be <= max_count")
        return self
```

**Changes at lock time (vs 2026-05-22 proposal):**
- **`messages` renamed to `model_responses`** — "messages" was ambiguous (excluded user messages, included tool messages, unclear on the multi-tool-call case). `model_responses` = count of assistant-role trace entries; one per LLM response.
- **Added `check_bounds` validator** — at least one bound must be set; `min <= max` when both set.

### Semantics

(Verified against actual Kiln trace shape 2026-06-02: trace is OpenAI-format `list[ChatCompletionMessageParam]` on `TaskRun.trace`; roles system / user / assistant / tool.)

- **`count_type="tool_calls"`** — count of individual tool-call requests across assistant messages ("how many calls the agent made")
- **`count_type="model_responses"`** — count of assistant-role entries in the trace (one per LLM response; an assistant message requesting N tool calls counts as **1**)
- **`count_type="turns"`** — count of user-role entries (one per user→assistant exchange; single-turn evals = 1; grounded in `parent_task_run_id` chaining)
- **`min_count` / `max_count`** — bounds; at least one required (validator); check passes when count is within bounds

**`model_responses` and `turns` do not collapse:** a single-turn run with 2 sequential tool calls has `model_responses=3`, `turns=1`, `tool_calls=2`. They coincide only in the degenerate no-tools single-turn case.

### Use cases this covers

```yaml
# "Agent should solve in ≤10 tool calls"
count_type: tool_calls
max_count: 10

# "Agent should take at least 2 user turns (rules out one-shot)"
count_type: turns
min_count: 2

# "Agent should make 3-7 model calls (efficiency band)"
count_type: messages
min_count: 3
max_count: 7
```

Covers Promptfoo's `trajectory:step-count` (1 of 5 trajectory assertion types).

### Cost

New EvalConfigType. Schema: ~20 LOC. Adapter: trace walker that counts items by `count_type` and compares to bounds — ~50 LOC. Total Phase 1 work: probably <100 LOC.

### Lock target

ALIGNMENT.md A2.4 catalog amendment: add `step_count_check` to V2.0 must-ship list (alongside the existing 6 + `code_eval`). New entry in `V2EvalType` enum. New `StepCountCheckProperties` Pydantic class. Adapter implementation in Phase 1.

---

## Coverage after both proposals lock

| Category | Promptfoo | Kiln V2.0 (with both) |
|---|---|---|
| Trajectory (tool called? in order? with args?) | 3 types | `tool_call_check` (1 type, expanded properties) |
| Efficiency (step count) | 1 type | `step_count_check` (new) |
| Outcome / goal-success | 1 type (LLM judge) | `llm_judge` + first-party "goal achievement" template (free) |
| Tool correctness | overlaps trajectory | overlaps via `tool_call_check` |

**Net:** parity with Promptfoo on the 4 categories with fewer (but well-designed) types.

---

## Open questions — RESOLVED at Batch J lock (2026-06-02)

- **Default `match_mode`:** ✅ **`all`** — clearest mental model ("I named these tools, all required").
- **`arg_match_mode` per-arg overrides:** ✅ **Per-arg** — `expected_args` is a dict of `{arg_name: ArgMatch{value, match_mode}}`. Top-level `arg_match_mode` removed. (Scalar-shorthand union deferred to Stage 5 `design/22`.)
- **Forbidden-tool check:** ✅ **Added `match_mode="never"`** (not in original proposal; Steve-requested at lock).
- **`step_count_check.count_type` extensibility (`tokens`):** ✅ **Out of scope for V2.0** — cost-eval territory, conceptually distinct. Additive later if asked.
- **`step_count_check.count_type` "turns" semantics:** ✅ **Resolved by sub-agent verification against actual Kiln source** — `turns` = count of user-role trace entries (one per exchange); `model_responses` (renamed from `messages`) = assistant-role entries. They are genuinely distinct, not collapsed. Single-turn + `count_type="turns"` = valid, counts 1.
- **Validator:** ✅ **Added** — at least one of min/max required; `min <= max`.
- **First-party "goal achievement" judge template:** ✅ **Punted to Stage 5 builder template authoring** — content, not catalog. Out of Batch J scope.

---

## Out of scope for V2.0 (post-V2 candidates)

- **`plan_adherence` / `plan_quality`** (DeepEval-style) — extracting an agent's plan from the trace is model-specific and hard to generalize. Better as `code_eval` (B.12) or a specialized `llm_judge` template if usage proves demand.
- **`event_ordering` DSL** — already deferred per B.14. If `tool_call_check` gets the `ordered` match mode (Proposal 37), the most common ordering case is covered without a separate DSL.
- **Multi-tool composition assertions** (e.g., "if tool A is called, tool B must follow within 3 steps") — DAG-shaped constraints. Defer to post-V2 alongside the `dag_metric` consideration.

---

## Decision/lock target

**Batch J** in `alignment_plan.md` — covers both Proposal 37 and Proposal 38. Output of Batch J: ALIGNMENT.md A2.4 amendments + (optional) new A2.x decision entries.

**Implementation downstream:** Stage 5 `design/22_type_deterministic_basics.md` (properties schemas), Phase 1 (adapters + new type wiring).

---

## Sources

- `reports/competitive_promptfoo.md` — trajectory assertion catalog
- `reports/competitive_deepeval.md` — agent metrics catalog
- `reports/competitive_inspect_ai.md` — scorer access to message history
- `reports/competitive_synthesis.md` §4 (agent eval row), §8 (best-in-class)
- Agent-eval gap-analysis sub-agent, 2026-05-22 (in conversation transcript)
- ALIGNMENT.md A2.4 (V2.0 type catalog lock)

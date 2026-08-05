---
status: draft
ship_gating: ship-blocker
scope: Manual (hand-driven) eval-config create UI — emit V2 + rebuild "Test Your Judge" + per-type form fixes
---

# Project: Manual eval create UI (V2)

## Summary

Rebuild Kiln's **manual** (hand-driven) eval-config create surface so that it (1) **emits V2 EvalConfigs** for the LLM-judge type instead of legacy V1 configs, (2) replaces the free-text "Test Your Judge" panel with the spec'd **dataset-item test harness**, and (3) fixes a set of per-type create-form defects. This is a single coherent rebuild of one surface — the create-eval-config page and the per-type form components — and should be done on one branch by one dev.

**Out of this project's scope:** the Copilot path and the questionnaire/`spec_builder` builder (a separate project), and the results/run-result viewing surfaces (a separate cleanup project). This project touches only the **create** flow.

## Authoritative design specs (already committed — read these)

- `specs/projects/evals_v2/components/70_builder_and_onboarding.md` — the create UI design. Especially:
  - **§1** — create-container architecture: standard Kiln **left = authoring form / right = "Test Run"** layout; the container (not each per-type form) owns loading test data (recent dataset items), running the test, and Save.
  - **§2** — the Test Run pane: *"lists recent dataset items to pick from. **Manual free-text input is cut.** Reference data is available via an **Advanced expander**; the trace comes from the selected dataset item."* Plus the empty-dataset state (*"Run your task to generate sample inputs"*), spinner + Cancel during run, and "a successful test run (valid shape vs `output_scores`) enables Save."
  - **§3.1** — the deterministic-type form field layouts (exact_match, pattern_match, contains, set_check, tool_call_check, step_count_check), including the radio-group vs literal/reference XOR, modes, and validation rules.
  - **§1 Type picker** — "LLM as Judge (recommended)" listed first, then the rest; all types always listed; Back returns to the picker.
- `specs/projects/evals_v2/components/21_type_llm_judge.md` — the V2 `llm_judge` design: the `prompt_template` model, the `g_eval` toggle, structured output, and **§6** (the create path: `system_prompt` is **not exposed** in the form; the adapter applies a default).
- `specs/projects/evals_v2/components/22_type_deterministic_basics.md` — the six deterministic `*Properties` shapes/modes the forms must produce.
- `specs/projects/evals_v2/components/40_template_and_extraction.md` — the Jinja2 template + `extract()` layer and `required_var` semantics (relevant to how the judge `prompt_template` is built).

---

## Problem statement — current state (what's wrong today)

### 1. The manual LLM-judge create flow still writes **V1** configs
- `app/web_ui/src/lib/components/eval_types/llm_judge_form.svelte` sets `selected_algo` to `"g_eval"` or `"llm_as_judge"` (lines ~136–163) and `getProperties()` returns `{ eval_steps, task_description }` (lines ~36–45) — i.e. the **V1** shape.
- `create_eval_config/+page.svelte` `do_save()` LLM branch (lines ~346–353) sets `config_type = getConfigType()` (g_eval/llm_as_judge) with those V1 properties.
- `app/desktop/studio_server/eval_api.py` `create_eval_config` (lines ~921–968) builds `EvalConfig(config_type=request.type, properties=request.properties, …)` — it passes the V1 type straight through.

Net: configs created from the manual UI are V1. They still *run* (via the legacy adapter), but the **enhanced V2 `llm_judge`** (per-criterion verdicts, Jinja `prompt_template`, `g_eval` as a typed property) is never produced from the UI.

### 2. "Test Your Judge" is free-text boxes, not a dataset-item harness
- In `create_eval_config/+page.svelte` the test panel is a `Collapse` titled "Test Your Judge" **below the form** (lines ~560–625) with four free-text inputs: `test_final_message` (textarea), `test_task_input` (input), `test_trace` (JSON textarea), `test_reference_data` (JSON textarea).
- It is gated on `can_submit_v2` (= a V2 type **and not** `llm_judge`, lines 205–206), so today the test panel is **not shown for the llm_judge path at all**, and no dataset items are ever loaded.

This contradicts `components/70 §1–§2`, which require a right-pane **Test Run** that lists **recent dataset items to pick from** (manual free-text is explicitly cut), with reference data behind an Advanced expander and the trace coming from the selected item.

### 3. Per-type create-form defects
- `set_check_form.svelte:7` defaults `mode: "equal"`, but the backend default is `"subset"` (`eval.py:145`, `SetCheckProperties.mode: Literal["subset","superset","equal"] = "subset"`). A user who doesn't touch the control silently gets strict equality.
- Four forms' value-expression help text says **"JSONPath"** (`exact_match_form.svelte:70`, `pattern_match_form.svelte:41`, `contains_form.svelte:81`, `set_check_form.svelte:88`) — but the engine is **Jinja2** (`extract()` / `compile_template_or_raise` in `libs/core/kiln_ai/utils/jinja_engine.py`). This teaches users the wrong syntax.
- The literal-vs-reference XOR "source" uses a `select` dropdown (`exact_match_form.svelte:33–46`, `contains_form.svelte:41–57`, `set_check_form.svelte:48–64`); `components/70 §3.1` specifies a **radio group** with the inactive input disabled.
- `tool_call_check_form.svelte`: `on_unexpected_tools` is always shown (lines ~98–108) — `§3.1` says hide it when match mode is "Never"; and `expected_args` is always visible — `§3.1` says collapse it by default.
- `set_check_form.svelte` `expected_set` is a one-per-line textarea (lines ~67–73); `§3.1` specifies a tag-input (add via enter/comma).
- The type picker (`app/web_ui/src/lib/utils/eval_types/registry.ts:39–48`) lists `llm_judge` 7th of 8, labeled "LLM Judge" with **no "(recommended)"** marker, and selecting a type doesn't push browser history (so Back doesn't return to the picker).

---

## Backend contracts you will use (already exist)

- **V2 `LlmJudgeProperties`** (`libs/core/kiln_ai/datamodel/eval.py:81–89`):
  ```python
  class LlmJudgeProperties(BaseModel):
      type: Literal[V2EvalType.llm_judge] = V2EvalType.llm_judge
      model_name: str
      model_provider: str
      system_prompt: str | None = None        # leave None — adapter defaults it; NOT exposed in the form
      prompt_template: str                     # required — the judge prompt (Jinja2)
      required_var: list[str] = []
      thinking_instruction: str | None = None
      g_eval: bool = False
  ```
  The adapter (`adapters/eval/v2_eval_llm_judge.py:47–50,118`) supplies a default system prompt when `system_prompt is None` — so the form must **not** expose it.
- **Create endpoint:** `POST /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/create_eval_config` already accepts `type: "v2"` with `properties` as the V2 discriminated union and optional `model_name`/`provider` (`CreateEvalConfigRequest`, `eval_api.py:185–201`). For a V2 `llm_judge`, POST `{ type: "v2", properties: <LlmJudgeProperties>, model_name, provider }`.
- **Test-run endpoint** (for the harness): `POST /api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/test_v2_eval` (`eval_api.py:971`). Request `TestV2EvalRequest { properties: V2EvalConfigProperties, eval_input: EvalTaskInput }`; response `TestV2EvalResponse { scores: dict[str,float], skipped_reason: str|None, skipped_detail: str|None }`. Frontend client: `testV2Eval()` in `app/web_ui/src/lib/api/v2_eval_api.ts`.
- **`EvalTaskInput`** (`eval.py:309–347`): `{ final_message: str, trace: list[dict]|None, reference_data: dict|None, task_input: str|None }`, with a `from_task_run(task_run)` classmethod (`final_message = output.output`, `trace = trace`, `reference_data = None`, `task_input = input`).
- **Loading recent dataset items** (for the picker): `GET /api/projects/{project_id}/tasks/{task_id}/runs` (full `TaskRun`s) or `GET .../runs_summaries` (lightweight: id, input/output previews, tags, rating). There is **no** eval-filter-specific endpoint; load runs and, if you want only the eval's dataset, filter client-side by the eval's `eval_set_filter_id` (tag-based). Map a chosen run → `EvalTaskInput` in the frontend: `final_message = run.output.output`, `task_input = run.input`, `trace = run.trace`, `reference_data = null` (offer the Advanced expander to add it).

---

## Work breakdown

### Phase 1 — Emit V2 from the manual LLM-judge path
**Goal:** the manual create flow produces a V2 `llm_judge` EvalConfig.
- Rework `llm_judge_form.svelte` to produce a `LlmJudgeProperties` object: collect the judge model + provider, the criteria/rubric, and the `g_eval` toggle, and build a `prompt_template`.
  - **Central design question (resolve first):** the form today collects `eval_steps` (a list) + `task_description`. V2 needs a single Jinja `prompt_template` (+ `required_var`). Decide how to construct it — recommended: keep the existing criteria/steps authoring UX and **generate** a `prompt_template` from it (task description + numbered criteria + scoring instructions, referencing the thing being judged via a template variable). Mirror how the V1 judge prompt was assembled from `eval_steps` (see the legacy `generate_*_run_description` logic referenced in `components/40`/`components/15`) and express it as a Jinja template. The template must reference a non-`reference_data` variable (the model output / task input) per `components/40`. Set `required_var` accordingly.
  - Map the existing logprob-based algo choice to the `g_eval` boolean (logprob-capable judge → `g_eval=True`).
  - Do **not** expose `system_prompt` (leave `None`).
- Update `create_eval_config/+page.svelte` `do_save()` so the llm_judge path POSTs `{ type: "v2", properties: <LlmJudgeProperties>, model_name, provider }`.
- No `create_eval_config` endpoint change is required (it already accepts V2), but verify round-trip save+load+run of a V2 `llm_judge` created this way.

### Phase 2 — Rebuild "Test Your Judge" as a dataset-item harness
Implement `components/70 §1–§2`:
- **Layout:** move the test pane to the **right** side (left = authoring form, right = "Test Run"), per the standard Kiln two-pane layout. (The current single-column collapse-below-form is the thing being replaced.)
- **Container loads recent dataset items:** call `/runs` (or `/runs_summaries`), show a picker of recent items (input/output preview); optionally filter to the eval's dataset.
- **Pick → Run → Results:** on pick, build the `EvalTaskInput` from the run; **remove the free-text `final_message`/`task_input`/`trace` inputs** (manual free-text is cut). Keep an **Advanced expander** to optionally supply `reference_data`. Run via `test_v2_eval`; show spinner + Cancel; render the returned scores / skip info.
- **Empty-dataset state:** if the task has no runs, show "Run your task to generate sample inputs" and make Save-Without-Testing the path.
- **Save gating:** a successful test run whose returned scores are a valid shape for the eval's `output_scores` enables Save (see `components/70 §2`). (Today `test_has_run` is set regardless of shape validity — fix so shape validity gates Save.)
- **Make the harness work for llm_judge too:** today it's excluded via `can_submit_v2`. After Phase 1, llm_judge is a V2 type and should get the same test harness.

### Phase 3 — Type picker + per-type form fixes
- **Type picker** (`registry.ts` + `+page.svelte` picker): order with **"LLM as Judge (recommended)"** first, then the rest; push browser history on select so Back returns to the picker (`components/70 §1`).
- **set_check default:** change the form default `mode` from `"equal"` to `"subset"` to match the backend (`set_check_form.svelte:7`). Also harden the API/datamodel so an empty/nil enum mode is rejected (require a real value) and ensure the form always submits a valid mode.
- **Help text:** change the four "JSONPath" strings to describe a **Jinja2 expression**, and add concrete examples in a tooltip (`components/70 §3.2` "value expression" guidance).
- **Form controls** (`components/70 §3.1`): convert the literal-vs-reference `select` to a **radio group** with the inactive input disabled (exact_match, contains, set_check); make `set_check.expected_set` a **tag-input** (enter/comma); **hide `on_unexpected_tools`** when match mode = "Never"; **collapse `expected_args`** by default in `tool_call_check`; add on-blur client validation with inline errors (regex compiles, min/max for step_count, etc.). These are lower priority and **descopable** if time-constrained.

---

## Acceptance criteria

- Creating an LLM judge from the manual UI persists an `EvalConfig` with `config_type == "v2"` and a valid `LlmJudgeProperties` (with a non-empty `prompt_template`); it loads and runs, producing scores for every `output_scores` entry.
- The Test Run pane lets the user **pick a recent dataset item** and run it (no free-text final_message/trace inputs); reference data is behind an Advanced expander; an empty dataset shows the guidance state; a valid-shape run enables Save.
- `set_check` created from the form uses `subset` unless the user changes it; value-expression help says Jinja2; the deterministic forms match `components/70 §3.1` (or the descoped subset is documented).
- All existing checks pass (`uv run ./checks.sh --agent-mode`; frontend `npm run check`/`lint`/`test_run`/`build`; OpenAPI schema in sync if any backend model changes).

## Out of scope (other projects)
- Copilot path and the questionnaire/`spec_builder` builder emitting V2 (separate project).
- Clone / prefill-from-existing and the read-only config-detail view (separate work).
- Run-result / comparison viewing surfaces (separate cleanup project).

## Open design questions
1. **`prompt_template` construction** (Phase 1) — generate from the existing criteria/steps UX, or redesign authoring to edit a template directly? Resolve before building Phase 1.
2. Should the test-run pane reuse a single component across all V2 types (incl. llm_judge), given the container already owns running the test uniformly? (Recommended yes.)
3. For the dataset-item picker, do we filter to the eval's `eval_set_filter_id` subset, or show all recent task runs? (Spec says "recent dataset items"; simplest is recent task runs, optionally filtered.)

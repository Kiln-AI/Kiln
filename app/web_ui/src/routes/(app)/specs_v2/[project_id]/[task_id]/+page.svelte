<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { agentInfo } from "$lib/agent"
  import { goto } from "$app/navigation"
  import { client, base_url } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"
  import { get_task_composite_id, load_task } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { get } from "svelte/store"
  import { isKilnAgentRunConfig } from "$lib/types"
  // Reuse v1 spec_builder components so v2 looks identical on the shared
  // screens (clarify Q&A, refine). When v1 evolves, v2 follows for free.
  import Questions from "../../../specs/[project_id]/[task_id]/spec_builder/questions.svelte"
  import RefineSpec from "../../../specs/[project_id]/[task_id]/spec_builder/refine_spec.svelte"
  import ReviewExamples from "../../../specs/[project_id]/[task_id]/spec_builder/review_examples.svelte"
  import { spec_field_configs } from "../../../specs/[project_id]/[task_id]/select_template/spec_templates"
  import type {
    SuggestedEdit,
    ReviewRow,
  } from "../../../specs/[project_id]/[task_id]/spec_utils"
  import { KilnError } from "$lib/utils/error_handlers"
  import type {
    Task,
    QuestionSet,
    QuestionWithAnswer,
    SpecType,
    SubsampleBatchOutputItemApi,
    SyntheticDataGenerationSessionConfigApi,
    SyntheticDataGenerationStepConfigApi,
    ReviewedExample,
  } from "$lib/types"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Evals V2",
    description: `V2 eval builder for project ${project_id}, task ${task_id} — single-page wizard for spec authoring with multi-turn support.`,
  })

  // ── State machine for the v2 builder.
  //   describe  — Step 1: free-text "what to evaluate"
  //   clarify   — Step 2: Q&A (no live preview — fast collection)
  //   refine    — Step 3: editable proposed spec edits (mirrors v1's refine screen)
  //   generate  — Step 4: single-turn examples or multi-turn chains
  //   review    — Step 5: pass/fail review + suggested spec refinements
  //   save      — Step 6: persist Spec + Eval + EvalConfig + dataset
  type BuilderStep =
    | "describe"
    | "clarify"
    | "refine"
    | "generate"
    | "review"
    | "save"
    | "done"
  let current_step: BuilderStep = "describe"
  const TOTAL_STEPS = 6
  const STEP_INDEX: Record<BuilderStep, number> = {
    describe: 1,
    clarify: 2,
    refine: 3,
    generate: 4,
    review: 5,
    save: 6,
    done: 6,
  }

  // ── Task (needed to know turn_mode for the Step 3 branch)
  let task: Task | null = null
  let task_loading = true
  let task_error: string | null = null
  $: is_multi_turn = task?.turn_mode === "multiturn"

  onMount(async () => {
    try {
      task = await load_task(project_id, task_id)
    } catch (e) {
      task_error = e instanceof Error ? e.message : "Failed to load task."
    } finally {
      task_loading = false
    }
  })

  // ── Step 1 state
  let description = ""
  // classify_spec_description should overwrite spec_type / name /
  // property_values when the kiln_server classifier ships. Defaulting to
  // "issue" keeps refine + save shapes valid in the meantime.
  let spec_type: SpecType = "issue"
  let name = ""
  let property_values: Record<string, string | null> = {
    issue_description: "",
    issue_examples: "",
    non_issue_examples: "",
  }
  let classifying = false
  let classify_error: string | null = null
  $: field_configs = spec_field_configs[spec_type]

  // Call classify_spec_description to map the free-text Step 1 description
  // to a spec_type + suggested name + structured property_values. The
  // endpoint currently returns 501 — on error we keep the "issue" defaults
  // so the user can still proceed and fill in property_values via the
  // Q&A / Refine steps.
  async function classify_then_continue() {
    classifying = true
    classify_error = null
    try {
      // Seed property_values.issue_description from the free-text description
      // up front. This is the fallback shape for the "issue" default — when
      // the classifier ships, it'll overwrite below. Done here so Step 3's
      // Refine "Original" column reflects what the user typed in Step 1
      // (and Step 2's refine_spec_with_question_answers has something to
      // refine from), even if classification fails.
      property_values = {
        ...property_values,
        issue_description: description,
      }

      const { data, error } = await client.POST(
        "/api/copilot/classify_spec_description",
        {
          body: {
            description,
            task_prompt: task?.instruction ?? null,
          },
        },
      )
      if (error || !data) {
        classify_error =
          "Couldn't classify your description — continuing with default 'issue' type."
        current_step = "clarify"
        return
      }
      spec_type = data.spec_type as SpecType
      name = data.suggested_name
      // The classifier returns the property_values dict already keyed for
      // this spec_type. Cast to the looser Record shape consumed by
      // Questions / RefineSpec.
      property_values = data.property_values as Record<string, string | null>
      current_step = "clarify"
    } catch (e) {
      classify_error =
        e instanceof Error ? e.message : "Couldn't classify your description."
    } finally {
      classifying = false
    }
  }

  // ── Step 2 state — questions
  let question_set: QuestionSet | null = null
  let questions_loading = false
  let questions_error: string | null = null
  let questions_form_error: KilnError | null = null
  let questions_submitting = false
  // Bound to the Questions component so selections survive remounts when
  // user navigates back from Refine to Clarify.
  let selections: (number | "other" | null)[] = []
  let other_texts: string[] = []

  async function load_questions() {
    questions_loading = true
    questions_error = null
    try {
      const { data, error } = await client.POST("/api/copilot/question_spec", {
        body: {
          target_task_info: {
            task_prompt: task?.instruction ?? "",
            task_input_schema: "",
            task_output_schema: "",
          },
          target_specification: description,
        },
      })
      if (error || !data) {
        questions_error = "Failed to load clarifying questions."
        return
      }
      question_set = data as QuestionSet
      selections = question_set.questions.map(() => null)
      other_texts = question_set.questions.map(() => "")
    } catch (e) {
      questions_error =
        e instanceof Error ? e.message : "Failed to load questions."
    } finally {
      questions_loading = false
    }
  }

  // ── Step 3 state — refine (shape required by v1's RefineSpec component)
  let refined_property_values: Record<string, string | null> = {}
  let suggested_edits: Record<string, SuggestedEdit> = {}
  let not_incorporated_feedback: string = ""
  let refine_form_error: KilnError | null = null
  let refine_submitting = false
  let refined_preview_loading = false

  // Called by Questions component on Continue. Fires the refinement call and
  // populates the state shape consumed by RefineSpec. Matches v1's flow:
  //   answer Qs → refining spinner → refine screen with editable suggestions.
  async function on_continue_from_clarify(
    questions_and_answers: QuestionWithAnswer[],
  ) {
    current_step = "refine"
    refined_preview_loading = true
    try {
      const spec_fields: Record<string, string> = {}
      const spec_field_current_values: Record<string, string> = {}
      for (const field of field_configs) {
        spec_fields[field.key] = field.description
        spec_field_current_values[field.key] = property_values[field.key] ?? ""
      }

      const { data, error } = await client.POST(
        "/api/copilot/refine_spec_with_question_answers",
        {
          body: {
            task_prompt: task?.instruction ?? "",
            specification: { spec_fields, spec_field_current_values },
            questions_and_answers,
          },
        },
      )
      if (error || !data) return

      const refine_response = data as {
        new_proposed_spec_edits?: {
          spec_field_name: string
          proposed_edit: string
          reason_for_edit?: string
        }[]
        not_incorporated_feedback?: string
      }

      // Start from current values, then apply each proposed edit. Mirrors v1's
      // processProposedSpecEdits helper in spec_builder/+page.svelte.
      const refined = { ...property_values }
      const edits: Record<string, SuggestedEdit> = {}
      for (const edit of refine_response.new_proposed_spec_edits ?? []) {
        refined[edit.spec_field_name] = edit.proposed_edit
        edits[edit.spec_field_name] = {
          proposed_value: edit.proposed_edit,
          reason_for_edit: edit.reason_for_edit ?? "",
        }
      }
      refined_property_values = refined
      suggested_edits = edits
      not_incorporated_feedback =
        refine_response.not_incorporated_feedback ?? ""
    } catch {
      // Silent — the refine response is optional; on error we land on the
      // refine step with no suggested edits and the user can advance.
    } finally {
      refined_preview_loading = false
    }
  }

  // Both events from RefineSpec — analyze_refined (user edited something)
  // and create_spec (no edits) — advance to Step 4 generation. v2 doesn't
  // re-analyze, it just uses whatever refined_property_values the user
  // finalized.
  function on_refine_submit() {
    // FormContainer flips submitting=true on every submit and leaves it to
    // the caller to reset. We dispatch the form forward immediately (no
    // network call here), so clear the flag before advancing — otherwise
    // RefineSpec's button stays disabled if the user navigates back.
    refine_submitting = false
    on_advance_to_generate()
  }

  // ── Step 3 state — generation
  let generation_loading = false
  let generation_error: string | null = null
  // single-turn output
  let single_turn_examples: SubsampleBatchOutputItemApi[] = []
  let sdg_session_config: SyntheticDataGenerationSessionConfigApi | null = null
  let judge_info: SyntheticDataGenerationStepConfigApi | null = null

  // multi-turn output — chains populated from real run_cases_batch SSE events.
  type ChainTurn = { role: "user" | "assistant"; content: string }
  type Chain = {
    case_index: number
    persona_summary: string
    total_cost: number
    trace: ChainTurn[]
  }
  // Number of synthetic-user cases to drive in one multi-turn batch —
  // matches NUM_CASES_MAX in libs/core/kiln_ai/synthetic_user/runner.py.
  const NUM_CASES = 10
  let multi_turn_chains: Chain[] = []
  let multi_turn_progress = 0 // 0..N as cases complete
  const multi_turn_total = NUM_CASES
  // Sub-phase for the Step 4 UI: distinguishes the up-front LLM call
  // (generate_cases) from the longer batch-run stream so the user sees
  // distinct progress instead of one ambiguous spinner.
  type MultiTurnPhase = "idle" | "generating_cases" | "running_batch"
  let multi_turn_phase: MultiTurnPhase = "idle"
  // Real batch_tag from run_cases_batch's BatchStartedEvent. The on_save
  // multi-turn branch uses this to tell the backend which chains to tag
  // for the eval dataset.
  let real_multi_turn_batch_tag: string | null = null

  async function on_generate_single_turn() {
    generation_loading = true
    generation_error = null
    try {
      const { data, error } = await client.POST("/api/copilot/clarify_spec", {
        body: {
          target_task_info: {
            task_prompt: task?.instruction ?? "",
            task_input_schema: "",
            task_output_schema: "",
          },
          target_specification: description,
          num_samples_per_topic: 10,
          num_topics: 10,
          providers: ["openrouter"],
          num_exemplars: 10,
        },
      })
      if (error || !data) {
        generation_error = "Failed to generate examples."
        return
      }
      single_turn_examples = data.examples_for_feedback ?? []
      sdg_session_config = data.sdg_session_config ?? null
      judge_info = data.judge_result ?? null
      current_step = "review"
    } catch (e) {
      generation_error = e instanceof Error ? e.message : "Generation failed."
    } finally {
      generation_loading = false
    }
  }

  // ── Step 4 multi-turn — drives real run_cases_batch SSE.
  //
  // Sequence:
  //   1. Pull the task's default run config → target_run_config for the
  //      drive loop. Multi-turn requires a KilnAgentRunConfig (the
  //      conversation needs an agent-shaped invoker).
  //   2. POST /multiturn_sdg/generate_cases → list of synthetic-user
  //      cases (seed prompt + persona blob).
  //   3. POST /multiturn_sdg/run_cases_batch as SSE; consume the stream
  //      and surface BatchEvent dispatch into component state.
  //
  // SU driver model is hardcoded for MVP (see design.md) — claude_4_5_haiku
  // via openrouter. Exposing the choice in the UI is deferred.
  const SU_DRIVER_DEFAULT = {
    model_name: "claude_4_5_haiku",
    model_provider: "openrouter",
  } as const
  const TURNS_PER_CASE = 5

  type SseEvent =
    | {
        event: "batch_started"
        batch_tag: string
        num_cases: number
      }
    | {
        event: "turn_completed"
        case_index: number
        assistant_run_id: string
        su_next_message: string
        cumulative_cost: number
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        trace: any[]
      }
    | {
        event: "case_completed"
        case_index: number
        chain_run_ids: string[]
        leaf_run_id: string
        total_turns: number
        total_cost: number
      }
    | {
        event: "case_failed"
        case_index: number
        error_code: string
        message: string
      }
    | {
        event: "batch_completed"
        successful: number
        failed: number
        batch_tag: string
        total_cost: number
      }

  async function on_generate_multi_turn() {
    generation_loading = true
    generation_error = null
    multi_turn_progress = 0
    multi_turn_chains = []
    real_multi_turn_batch_tag = null
    multi_turn_phase = "idle"

    try {
      // 1. Resolve target_run_config: prefer the task's default; if none
      // set, fall back to the first available run config so the user
      // doesn't have to detour into task settings just to try v2. Only
      // error when the task has zero configs (genuinely unrunnable).
      if (!task?.id) {
        generation_error = "Task not loaded."
        return
      }
      await load_task_run_configs(project_id, task.id)
      const run_configs =
        get(run_configs_by_task_composite_id)[
          get_task_composite_id(project_id, task.id)
        ] ?? []
      if (run_configs.length === 0) {
        generation_error =
          "Task has no run configs — create one before running multi-turn."
        return
      }
      const chosen_config =
        run_configs.find((c) => c.id === task!.default_run_config_id) ??
        run_configs[0]
      const rcp = chosen_config.run_config_properties
      if (!isKilnAgentRunConfig(rcp)) {
        generation_error =
          "Multi-turn requires a Kiln Agent run config; the selected one isn't."
        return
      }
      const target_run_config = {
        model_name: rcp.model_name,
        model_provider: rcp.model_provider_name,
        prompt_id: rcp.prompt_id ?? "simple_prompt_builder",
      }

      // 2. Generate synthetic-user cases via copilot.
      multi_turn_phase = "generating_cases"
      const refined_description =
        (refined_property_values.issue_description as string | null) ??
        description
      const cases_resp = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases",
        {
          params: { path: { project_id, task_id } },
          body: {
            target_specification: refined_description,
            num_cases: NUM_CASES,
          },
        },
      )
      if (cases_resp.error || !cases_resp.data) {
        generation_error = "Failed to generate synthetic-user cases."
        return
      }

      // 3. Stream run_cases_batch. The endpoint is POST so we can't use
      // EventSource (which is GET-only). Manual fetch + ReadableStream +
      // SSE line parsing — same pattern as streaming_chat.ts.
      multi_turn_phase = "running_batch"
      const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/multiturn_sdg/run_cases_batch`
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          cases: cases_resp.data.cases,
          turns: TURNS_PER_CASE,
          target_run_config,
          su_driver: SU_DRIVER_DEFAULT,
        }),
      })

      if (!response.ok || !response.body) {
        let detail: string
        try {
          const err_json = await response.json()
          detail = err_json?.message ?? err_json?.detail?.message ?? "unknown"
        } catch {
          detail = await response.text().catch(() => "unknown")
        }
        generation_error = `run_cases_batch failed (${response.status}): ${detail}`
        return
      }

      // Per-case cumulative trace from turn_completed events. The leaf's
      // trace at case_completed time is what we render on the review cards.
      const traces_by_case: Record<number, ChainTurn[]> = {}
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      stream_loop: while (true) {
        const { done, value } = await reader.read()
        if (done) break stream_loop
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const payload = line.slice(6).trim()
          if (!payload) continue
          let event: SseEvent
          try {
            event = JSON.parse(payload) as SseEvent
          } catch {
            continue
          }

          if (event.event === "batch_started") {
            real_multi_turn_batch_tag = event.batch_tag
          } else if (event.event === "turn_completed") {
            // event.trace is OpenAI-format messages; project to ChainTurn.
            const turns: ChainTurn[] = (event.trace ?? [])
              .map((msg) => ({
                role: msg.role as ChainTurn["role"],
                content:
                  typeof msg.content === "string"
                    ? msg.content
                    : JSON.stringify(msg.content),
              }))
              .filter(
                (t: ChainTurn) => t.role === "user" || t.role === "assistant",
              )
            traces_by_case[event.case_index] = turns
          } else if (event.event === "case_completed") {
            multi_turn_chains = [
              ...multi_turn_chains,
              {
                case_index: event.case_index,
                persona_summary: `Case ${event.case_index + 1}`,
                total_cost: event.total_cost ?? 0,
                trace: traces_by_case[event.case_index] ?? [],
              },
            ]
            multi_turn_progress = multi_turn_chains.length
          } else if (event.event === "case_failed") {
            console.warn(
              `SU case ${event.case_index} failed: ${event.error_code} ${event.message}`,
            )
          } else if (event.event === "batch_completed") {
            break stream_loop
          }
        }
      }

      if (multi_turn_chains.length === 0) {
        generation_error =
          "All synthetic-user cases failed — check task and SU driver model availability."
        return
      }

      current_step = "review"
    } catch (e) {
      generation_error =
        e instanceof Error ? e.message : "Multi-turn generation failed."
    } finally {
      generation_loading = false
    }
  }

  function on_continue_from_generate_step() {
    if (is_multi_turn) {
      on_generate_multi_turn()
    } else {
      on_generate_single_turn()
    }
  }

  // Advance from the Refine step (3) into Generate (4) and immediately kick
  // off generation — no extra click required. The in-step button only
  // surfaces if generation errored, as a retry affordance.
  function on_advance_to_generate() {
    current_step = "generate"
    on_continue_from_generate_step()
  }

  // Same pattern for Review (5) → Save (6): land on Save with the request
  // already in flight; only show the in-step button on error as retry.
  function on_advance_to_save() {
    current_step = "save"
    on_save()
  }

  // ── Step 5 state — single-turn review (uses v1's ReviewExamples)
  // ReviewRow is the shape ReviewExamples reads/mutates internally —
  // it bumps user_says_meets_spec + feedback on each pass/fail click.
  let review_rows: ReviewRow[] = []
  let review_form_error: KilnError | null = null
  let review_submitting = false
  // Convert generation output to ReviewRow shape when examples become
  // available (Step 4 → Step 5 transition). Only initializes — subsequent
  // user edits stay on the array.
  $: if (
    single_turn_examples.length > 0 &&
    review_rows.length !== single_turn_examples.length
  ) {
    review_rows = single_turn_examples.map((e, i) => ({
      input: e.input,
      output: e.output,
      model_says_meets_spec: !e.fails_specification,
      feedback: "",
      row_id: `row_${i}`,
    }))
  }

  // Multi-turn: per-chain pass/fail
  let chain_verdicts: Array<{
    verdict: "pass" | "fail" | null
    feedback: string
  }> = []
  $: chain_verdicts =
    multi_turn_chains.length > 0 &&
    chain_verdicts.length !== multi_turn_chains.length
      ? multi_turn_chains.map(() => ({ verdict: null, feedback: "" }))
      : chain_verdicts

  // ── Step 6 state — save
  let saving = false
  let save_error: string | null = null

  // Fetch a default judge_info via clarify_spec for the multi-turn save
  // path. The clarify_spec response also includes single-turn examples and
  // sdg_session_config which we ignore — multi-turn save uses neither.
  // Stopgap until a dedicated "default judge config" endpoint ships.
  // clarify_spec is single-turn-specific but its response includes a
  // judge_result that's reusable as the multi-turn save's judge_info.
  async function fetch_judge_info_via_clarify_spec() {
    const { data, error } = await client.POST("/api/copilot/clarify_spec", {
      body: {
        target_task_info: {
          task_prompt: task?.instruction ?? "",
          task_input_schema: "",
          task_output_schema: "",
        },
        target_specification: description,
        num_samples_per_topic: 10,
        num_topics: 10,
        providers: ["openrouter"],
        num_exemplars: 10,
      },
    })
    if (error || !data) return false
    judge_info = data.judge_result ?? null
    return judge_info !== null
  }

  async function on_save() {
    saving = true
    save_error = null
    try {
      // Source of truth for the saved spec is refined_property_values —
      // populated from Step 1 description initially, then updated in Step 3
      // via v1's RefineSpec component when the user accepts/edits the LLM's
      // proposed refinements. Fall back to property_values if Step 3 was
      // skipped (no refinements were proposed).
      const final_values =
        Object.keys(refined_property_values).length > 0
          ? refined_property_values
          : property_values
      const issue_description = final_values.issue_description ?? description
      const filtered = Object.fromEntries(
        Object.entries(final_values).filter(
          ([_, v]) => v !== null && v !== "" && (v ?? "").trim() !== "",
        ),
      )
      const spec_properties = {
        spec_type: "issue" as const,
        ...filtered,
        issue_description,
      }

      // Multi-turn save: tag the chains produced by run_cases_batch.
      // judge_info isn't carried through the multi-turn pipeline so we
      // fetch one via clarify_spec — wasteful but works until a dedicated
      // "default judge config" endpoint ships.
      if (is_multi_turn) {
        if (real_multi_turn_batch_tag === null) {
          save_error =
            "No multi-turn chains were generated — go back to Step 4."
          return
        }
        const ok = await fetch_judge_info_via_clarify_spec()
        if (!ok || !judge_info) {
          save_error = "Save failed — couldn't fetch judge config."
          return
        }
        const { data, error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot",
          {
            params: { path: { project_id, task_id } },
            body: {
              name,
              definition: issue_description,
              properties: spec_properties,
              evaluate_full_trace: true,
              reviewed_examples: [],
              judge_info,
              multi_turn: { batch_tag: real_multi_turn_batch_tag },
              task_description: "",
              task_prompt_with_example: task?.instruction ?? "",
            },
          },
        )
        if (error || !data) {
          save_error = "Save failed — try again."
          return
        }
        const saved = data as { id?: string }
        if (saved.id) {
          goto(`/specs/${project_id}/${task_id}/${saved.id}`)
        } else {
          current_step = "done"
        }
        return
      }

      // Single-turn save path.
      const reviewed_examples: ReviewedExample[] = review_rows
        .filter((row) => row.user_says_meets_spec !== undefined)
        .map((row) => ({
          input: row.input,
          output: row.output,
          model_says_meets_spec: row.model_says_meets_spec,
          user_says_meets_spec: row.user_says_meets_spec as boolean,
          feedback: row.feedback,
        }))

      if (!sdg_session_config || !judge_info) {
        save_error =
          "Missing generation config — go back to Step 4 and regenerate."
        return
      }

      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/spec_with_copilot",
        {
          params: { path: { project_id, task_id } },
          body: {
            name,
            definition: issue_description,
            properties: spec_properties,
            evaluate_full_trace: false,
            reviewed_examples,
            judge_info,
            sdg_session_config,
            task_description: "",
            task_prompt_with_example: task?.instruction ?? "",
          },
        },
      )
      if (error || !data) {
        save_error = "Save failed — try again."
        return
      }
      // Land on the spec/eval detail page (titled "Eval: ..."). This is
      // the same destination v1 uses.
      const saved = data as { id?: string }
      if (saved.id) {
        goto(`/specs/${project_id}/${task_id}/${saved.id}`)
      } else {
        current_step = "done"
      }
    } catch (e) {
      save_error = e instanceof Error ? e.message : "Save failed."
    } finally {
      saving = false
    }
  }

  // ── Navigation helpers
  function back_to_task() {
    goto(`/specs/${project_id}/${task_id}`)
  }

  // Auto-load questions when entering Step 2
  $: if (current_step === "clarify" && !question_set && !questions_loading) {
    load_questions()
  }
</script>

<AppPage
  title="Evals V2"
  subtitle="A simplified eval builder — beta"
  no_y_padding
>
  <div class="max-w-3xl mx-auto py-6">
    <!-- Step indicator -->
    <div class="text-xs text-gray-500 mb-6 flex items-center gap-2">
      <span>Step</span>
      <span class="font-medium">{STEP_INDEX[current_step]}</span>
      <span>of {TOTAL_STEPS}</span>
      {#if is_multi_turn}
        <span class="badge badge-secondary badge-sm ml-2">multi-turn</span>
      {/if}
    </div>

    {#if task_loading}
      <div class="text-center text-gray-500 py-12">Loading task…</div>
    {:else if task_error}
      <div class="alert alert-error">{task_error}</div>
    {:else if current_step === "describe"}
      <!-- ── Step 1 — Describe ── -->
      <h1 class="text-2xl font-bold mb-2">What should this eval check?</h1>
      <p class="text-sm text-gray-500 mb-4">
        Describe in plain language. We'll structure it for you.
      </p>

      <FormElement
        label=""
        id="description"
        inputType="textarea"
        height="medium"
        bind:value={description}
      />

      <div class="text-xs text-gray-400 mt-2">
        Spec name (auto-derived after Continue)
      </div>

      {#if classify_error}
        <div class="alert alert-warning mt-3 text-sm">{classify_error}</div>
      {/if}

      <div class="flex justify-between mt-8">
        <button class="btn btn-ghost" on:click={back_to_task}>← Cancel</button>
        <button
          class="btn btn-primary"
          on:click={classify_then_continue}
          disabled={!description.trim() || classifying}
        >
          {#if classifying}
            <span class="loading loading-dots loading-sm"></span>
            Classifying…
          {:else}
            Continue →
          {/if}
        </button>
      </div>
    {:else if current_step === "clarify"}
      <!-- ── Step 2 — Clarify (uses v1's Questions component) ── -->
      {#if questions_loading}
        <div class="text-center text-gray-500 py-8">
          <span class="loading loading-dots loading-md"></span>
          <div class="text-xs mt-2">Generating clarifying questions…</div>
        </div>
      {:else if questions_error}
        <div class="alert alert-error">{questions_error}</div>
      {:else if question_set}
        <Questions
          {name}
          {spec_type}
          {property_values}
          {question_set}
          bind:selections
          bind:other_texts
          on_submit={on_continue_from_clarify}
          bind:error={questions_form_error}
          bind:submitting={questions_submitting}
          warn_before_unload={false}
        />
        <div class="mt-4">
          <button
            class="btn btn-ghost btn-sm"
            on:click={() => (current_step = "describe")}>← Back</button
          >
        </div>
      {/if}
    {:else if current_step === "refine"}
      <!-- ── Step 3 — Refine ── -->
      {#if refined_preview_loading}
        <div class="text-center py-12">
          <span class="loading loading-dots loading-lg"></span>
          <div class="text-sm mt-4 text-gray-500">Refining your eval…</div>
        </div>
      {:else if is_multi_turn}
        <!-- Multi-turn variant: examples fields don't apply (real examples
             come from Step 4 synthetic chains). Just name + description. -->
        <h1 class="text-2xl font-bold mb-2">Refine your eval</h1>
        <p class="text-sm text-gray-500 mb-6">
          Review the refined description below. The synthetic-user run in Step 4
          will probe your agent against this spec.
        </p>

        <div class="mb-6">
          <FormElement
            label="Eval Name"
            description="A short name for your own reference."
            id="multi_turn_name"
            inputType="input"
            bind:value={name}
          />
        </div>

        <div class="mb-4">
          <FormElement
            label="Issue Description"
            description="What the agent must avoid doing."
            id="multi_turn_issue_description"
            inputType="textarea"
            height="large"
            bind:value={refined_property_values.issue_description}
          />
          {#if suggested_edits.issue_description?.reason_for_edit}
            <div class="text-xs text-gray-500 italic mt-2">
              Refinement: {suggested_edits.issue_description.reason_for_edit}
            </div>
          {/if}
        </div>

        {#if not_incorporated_feedback}
          <div class="alert alert-info text-sm mb-4">
            <span class="font-medium">Unincorporated feedback:</span>
            {not_incorporated_feedback}
          </div>
        {/if}

        <div class="flex justify-between mt-8">
          <button
            class="btn btn-ghost btn-sm"
            on:click={() => (current_step = "clarify")}>← Back</button
          >
          <button
            class="btn btn-primary"
            on:click={on_refine_submit}
            disabled={!name.trim() ||
              !(refined_property_values.issue_description ?? "").trim()}
          >
            Generate conversations →
          </button>
        </div>
      {:else}
        <!-- Single-turn variant: keep v1's RefineSpec component (handles
             examples, two-column diff, restore-suggestion buttons). -->
        <RefineSpec
          bind:name
          original_property_values={property_values}
          bind:refined_property_values
          {suggested_edits}
          {not_incorporated_feedback}
          {field_configs}
          bind:error={refine_form_error}
          bind:submitting={refine_submitting}
          warn_before_unload={false}
          hide_secondary_button={true}
          on:analyze_refined={on_refine_submit}
          on:create_spec={on_refine_submit}
        />
        <div class="mt-4">
          <button
            class="btn btn-ghost btn-sm"
            on:click={() => (current_step = "clarify")}>← Back</button
          >
        </div>
      {/if}
    {:else if current_step === "generate"}
      <!-- ── Step 4 — Generate ── -->
      <h1 class="text-2xl font-bold mb-2">
        {#if is_multi_turn && multi_turn_phase === "generating_cases"}
          Generating {NUM_CASES} synthetic-user cases
        {:else if is_multi_turn}
          Running synthetic conversations
        {:else}
          Generating examples
        {/if}
      </h1>
      <p class="text-sm text-gray-500 mb-6">
        {#if is_multi_turn && multi_turn_phase === "generating_cases"}
          Asking the copilot to author {NUM_CASES} persona-driven scenarios that
          probe your spec.
        {:else if is_multi_turn}
          Driving {multi_turn_total} cases against your agent. This will take a moment.
        {:else}
          Generating ~10 sample inputs and outputs based on your spec.
        {/if}
      </p>

      {#if generation_loading}
        <div class="text-center py-12">
          <span class="loading loading-dots loading-lg"></span>
          {#if is_multi_turn && multi_turn_phase === "generating_cases"}
            <div class="text-sm mt-4 text-gray-500">
              Generating {NUM_CASES} cases…
            </div>
          {:else if is_multi_turn}
            <div class="text-sm mt-4 text-gray-500">
              {multi_turn_progress} of {multi_turn_total} ready
            </div>
          {:else}
            <div class="text-sm mt-4 text-gray-500">Generating examples…</div>
          {/if}
        </div>
      {/if}

      {#if generation_error}
        <div class="alert alert-error mt-4">{generation_error}</div>
        <div class="text-center py-4">
          <button
            class="btn btn-primary"
            on:click={on_continue_from_generate_step}
          >
            Retry →
          </button>
        </div>
      {/if}

      <div class="flex justify-between mt-8">
        <button
          class="btn btn-ghost"
          on:click={() => (current_step = "clarify")}
          disabled={generation_loading}>← Back</button
        >
      </div>
    {:else if current_step === "review"}
      <!-- ── Step 5 — Review ── -->
      {#if is_multi_turn}
        <h1 class="text-2xl font-bold mb-2">Review</h1>
        <p class="text-sm text-gray-500 mb-6">
          Read each conversation. Mark each chain Pass or Fail.
        </p>
        <!-- Multi-turn: custom card stack of conversation traces.
             v1's ReviewExamples only handles single I/O pairs, so multi-turn
             keeps its own UI. -->
        <div class="space-y-4">
          {#each multi_turn_chains as chain, ci}
            <div class="card bg-base-200 shadow-sm">
              <div class="card-body p-4">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex-1">
                    <div class="text-xs text-gray-500 mb-1">
                      Conversation {ci + 1} of {multi_turn_chains.length}
                    </div>
                    <div class="text-xs italic text-gray-500">
                      {chain.persona_summary}
                    </div>
                  </div>
                  <div class="flex gap-1">
                    <button
                      class="btn btn-xs {chain_verdicts[ci]?.verdict === 'fail'
                        ? 'btn-error'
                        : 'btn-outline'}"
                      on:click={() => {
                        chain_verdicts[ci].verdict = "fail"
                        chain_verdicts = [...chain_verdicts]
                      }}
                    >
                      ✗ Fail
                    </button>
                    <button
                      class="btn btn-xs {chain_verdicts[ci]?.verdict === 'pass'
                        ? 'btn-success'
                        : 'btn-outline'}"
                      on:click={() => {
                        chain_verdicts[ci].verdict = "pass"
                        chain_verdicts = [...chain_verdicts]
                      }}
                    >
                      ✓ Pass
                    </button>
                  </div>
                </div>

                <div class="mt-3 space-y-2 text-sm">
                  {#each chain.trace as turn}
                    <div
                      class="rounded px-3 py-2 {turn.role === 'user'
                        ? 'bg-base-100'
                        : 'bg-primary/10'}"
                    >
                      <div class="text-xs text-gray-500 mb-1">
                        {turn.role}
                      </div>
                      <div class="whitespace-pre-wrap">{turn.content}</div>
                    </div>
                  {/each}
                </div>

                {#if chain_verdicts[ci]?.verdict !== null}
                  <input
                    type="text"
                    class="input input-bordered input-sm mt-3"
                    placeholder="Feedback (optional)"
                    bind:value={chain_verdicts[ci].feedback}
                  />
                {/if}
              </div>
            </div>
          {/each}
        </div>
        <div class="flex justify-between mt-8">
          <button
            class="btn btn-ghost"
            on:click={() => (current_step = "generate")}>← Back</button
          >
          <button class="btn btn-primary" on:click={on_advance_to_save}>
            Save →
          </button>
        </div>
      {:else}
        <!-- Single-turn: reuse v1's ReviewExamples component. Both submit
             events (create_spec when feedback aligns, continue_to_refine
             when it doesn't) advance to Save in v2 — we don't re-loop
             through refine after review. -->
        <ReviewExamples
          {name}
          {spec_type}
          {property_values}
          bind:review_rows
          bind:error={review_form_error}
          bind:submitting={review_submitting}
          warn_before_unload={false}
          on:create_spec={on_advance_to_save}
          on:continue_to_refine={on_advance_to_save}
          on:create_spec_secondary={on_advance_to_save}
        />
        <div class="mt-4">
          <button
            class="btn btn-ghost btn-sm"
            on:click={() => (current_step = "generate")}>← Back</button
          >
        </div>
      {/if}
    {:else if current_step === "save"}
      <!-- ── Step 5 — Save ── -->
      <h1 class="text-2xl font-bold mb-2">Save</h1>
      <p class="text-sm text-gray-500 mb-6">
        Creating the Spec, Eval, and dataset…
      </p>

      {#if saving}
        <div class="text-center py-12">
          <span class="loading loading-dots loading-lg"></span>
          <div class="text-sm mt-4 text-gray-500">Saving…</div>
        </div>
      {:else if save_error}
        <div class="alert alert-error">{save_error}</div>
        <div class="text-center py-4">
          <button class="btn btn-primary" on:click={on_save}>Retry →</button>
        </div>
      {/if}

      <div class="flex justify-between mt-8">
        <button
          class="btn btn-ghost"
          on:click={() => (current_step = "review")}
          disabled={saving}>← Back</button
        >
      </div>
    {:else if current_step === "done"}
      <!-- Fallback: save succeeded but no eval_id/spec_id to redirect to. -->
      <div class="text-center py-12">
        <div class="text-4xl mb-4">✓</div>
        <h1 class="text-2xl font-bold mb-2">Spec saved</h1>
        <button class="btn btn-primary" on:click={back_to_task}>
          Back to evals
        </button>
      </div>
    {/if}
  </div>
</AppPage>

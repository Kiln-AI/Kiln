<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { agentInfo } from "$lib/agent"
  import { goto, pushState, replaceState } from "$app/navigation"
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
  import Questions from "../spec_builder/questions.svelte"
  import RefineSpec from "../spec_builder/refine_spec.svelte"
  // Claim/Evidence replaces the read-the-trace pass/fail review: the reviewer
  // agrees/disagrees with distilled claims; the trace stays hidden in a modal.
  import ClaimEvidenceReview from "./claim_evidence_review.svelte"
  // Multi-turn Step 4 is plan-first: the batch planner drafts one scenario
  // per conversation for approval before any conversation is driven.
  import BatchPlanApproval from "./batch_plan_approval.svelte"
  import { multiturn_plan_guidance } from "./batch_plan_guidance"
  import {
    all_traces_reviewed,
    build_claim_review_payload,
    build_trace_reviews,
    disagreement_feedback,
    user_says_meets_spec,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"
  // Reuse v1's themed loading animations on the wizard's transition screens
  // instead of bare dot-spinners, so the two builders feel consistent.
  import QuestioningAnimation from "$lib/ui/animations/questioning_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import SavingAnimation from "$lib/ui/animations/saving_animation.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import type { SuggestedEdit } from "../spec_utils"
  import { KilnError } from "$lib/utils/error_handlers"
  import { filename_string_short_validator } from "$lib/utils/input_validators"
  import { build_default_judge_info } from "$lib/eval/default_judge"
  import {
    kilnCopilotConnected,
    initCopilotConnectionStore,
  } from "$lib/stores/copilot_connection_store"
  import CopilotRequiredCard from "$lib/ui/kiln_copilot/copilot_required_card.svelte"
  import Warning from "$lib/ui/warning.svelte"
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
  import posthog from "posthog-js"

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
  let last_tracked_step: BuilderStep | null = null
  $: if (current_step !== last_tracked_step && task) {
    last_tracked_step = current_step
    posthog.capture("eval_v2_step_entered", {
      step: current_step,
      is_multi_turn,
    })
  }
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

  // AbortController for in-flight Copilot requests. Mirrors v1 spec_builder:
  // starting a new request implicitly cancels any prior one (no stale
  // responses overwriting newer state), and Back buttons call
  // abort_copilot_request() so cancelling out of a loading step also kills
  // the request instead of leaving it running in the background.
  let copilot_abort_controller: AbortController | null = null

  function abort_copilot_request() {
    copilot_abort_controller?.abort()
    copilot_abort_controller = null
  }

  function new_copilot_abort_signal(): AbortSignal {
    abort_copilot_request()
    copilot_abort_controller = new AbortController()
    return copilot_abort_controller.signal
  }

  function is_abort_error(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError"
  }

  // ── Navigation (Svelte shallow routing).
  //
  // Each step transition records the step in history.state, so the browser's
  // own Back/Forward move between steps — the component stays mounted, so no
  // data is lost — instead of leaving the builder. popstate then restores the
  // correct step (fixing the old "Back jumps to the wrong step" bug). The step
  // is just a value in history.state, not a per-step route, so this survives
  // any future change to the set of steps.
  //
  //   goto_step    — forward to a step the user dwells on (pushes an entry).
  //   replace_step — swap the current entry for a result step, so transient
  //                  loading steps (single-turn generate, save) don't become
  //                  Back targets. Multi-turn generate holds the interactive
  //                  plan-approval view, so review is PUSHED over it instead.
  function goto_step(next: BuilderStep) {
    current_step = next
    pushState("", { builder_step: next })
  }
  function replace_step(next: BuilderStep) {
    current_step = next
    replaceState("", { builder_step: next })
  }

  // Restore the step on browser Back/Forward. Equality-guarded so our own
  // push/replace (which also update page.state) are no-ops here; only real
  // history navigation changes the step — and when it does, abort any in-flight
  // request so a cancelled loading step doesn't leave a stuck spinner.
  function sync_step_from_history(step: BuilderStep | undefined) {
    if (!step || step === current_step) return
    abort_copilot_request()
    current_step = step
  }
  $: sync_step_from_history(
    ($page.state as { builder_step?: BuilderStep }).builder_step,
  )

  // Warn before a full reload/close/external-nav when there's unsaved work —
  // history can't guard a real unload (mirrors v1's warn_before_unload). SPA
  // transitions (the save redirect) don't trigger beforeunload, so a successful
  // save won't spuriously prompt.
  $: warn_before_unload = current_step !== "describe" && current_step !== "done"
  function handle_before_unload(event: BeforeUnloadEvent) {
    if (!warn_before_unload) return
    event.preventDefault()
    event.returnValue = ""
  }

  // ── Task (drives is_multi_turn, which branches Step 3 onward)
  let task: Task | null = null
  let task_loading = true
  let task_error: string | null = null
  $: is_multi_turn = task?.turn_mode === "multiturn"

  onMount(async () => {
    // Seed the first history entry with the starting step so Back from Step 2
    // returns to Step 1 rather than leaving the builder.
    replaceState("", { builder_step: current_step })
    initCopilotConnectionStore()
    try {
      task = await load_task(project_id, task_id)
      posthog.capture("eval_v2_builder_opened", {
        is_multi_turn: task?.turn_mode === "multiturn",
      })
    } catch (e) {
      task_error = e instanceof Error ? e.message : "Failed to load task."
    } finally {
      task_loading = false
    }
  })

  onDestroy(() => {
    abort_copilot_request()
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
      // Refine reflects what the user typed in Step 1 (and Step 2's
      // refine_spec_with_question_answers has something to refine from),
      // even if classification fails.
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
          signal: new_copilot_abort_signal(),
        },
      )
      if (error || !data) {
        classify_error =
          "Couldn't classify your description — continuing with default 'issue' type."
        goto_step("clarify")
        return
      }
      spec_type = data.spec_type as SpecType
      name = data.suggested_name
      // The classifier returns the property_values dict already keyed for
      // this spec_type. Cast to the looser Record shape consumed by
      // Questions / RefineSpec.
      property_values = data.property_values as Record<string, string | null>
      goto_step("clarify")
    } catch (e) {
      if (is_abort_error(e)) return
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
        signal: new_copilot_abort_signal(),
      })
      if (error || !data) {
        questions_error = "Failed to load clarifying questions."
        return
      }
      question_set = data as QuestionSet
      selections = question_set.questions.map(() => null)
      other_texts = question_set.questions.map(() => "")
    } catch (e) {
      if (is_abort_error(e)) return
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
    goto_step("refine")
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
          signal: new_copilot_abort_signal(),
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

  // ── Step 4 state — generation
  let generation_loading = false
  let generation_error: string | null = null
  let single_turn_examples: SubsampleBatchOutputItemApi[] = []
  let sdg_session_config: SyntheticDataGenerationSessionConfigApi | null = null
  let judge_info: SyntheticDataGenerationStepConfigApi | null = null

  // multi-turn output — chains populated from run_cases_batch SSE events.
  type ChainTurn = { role: "user" | "assistant"; content: string }
  type Chain = {
    case_index: number
    persona_summary: string
    total_cost: number
    trace: ChainTurn[]
    // Durable id of the chain's leaf TaskRun (from case_completed) — the save
    // path writes the golden rating onto this run.
    leaf_run_id: string
  }
  // Number of synthetic-user cases to drive in one multi-turn batch —
  // matches NUM_CASES_MAX in libs/core/kiln_ai/synthetic_user/runner.py.
  const NUM_CASES = 10
  let multi_turn_chains: Chain[] = []
  let multi_turn_progress = 0 // 0..N as cases complete
  // Batch plan for multi-turn Step 4 — one scenario prompt per conversation,
  // drafted by the copilot batch planner and approved (with edits/deletions)
  // by the user before any conversation is driven.
  type BatchPlan = { prompts: string[]; summary: string }
  let batch_plan: BatchPlan | null = null
  // The summary isn't regenerated when the user edits/deletes prompts — flag
  // that it may no longer match (mirrors the /generate route's plan UI).
  let batch_plan_edited = false
  // Snapshot of the prompts a drive actually ran — gates "Continue to Review"
  // so results are never presented for a plan edited after the drive.
  let driven_prompts_json: string | null = null
  // Approved plan length drives the batch size; NUM_CASES is the requested
  // plan size before any deletions.
  $: multi_turn_total = batch_plan?.prompts.length ?? NUM_CASES
  // Total assistant turns streamed so far (one per turn_completed event),
  // across all cases. Drives a smooth progress indicator: cases complete in
  // concurrency-limited waves, so a case-only count sits still then jumps —
  // counting turns instead makes steady progress visible while the backend
  // works in parallel.
  let multi_turn_turns_done = 0
  // Which loading stage Step 4 is in — drives the spinner title/caption only.
  // The interactive plan-approval view is DERIVED (show_plan_approval below),
  // not a phase, so no code path can strand it behind a stale flag.
  type MultiTurnPhase =
    | "idle"
    | "planning"
    | "generating_cases"
    | "running_batch"
    | "reviewing"
  let multi_turn_phase: MultiTurnPhase = "idle"
  $: show_plan_approval =
    is_multi_turn &&
    batch_plan !== null &&
    !generation_loading &&
    !generation_error
  // batch_tag from run_cases_batch's BatchStartedEvent — passed to the
  // save endpoint so the backend can tag the matching chains for the
  // eval dataset.
  let multi_turn_batch_tag: string | null = null
  // Set when on_generate_multi_turn had to fall back to the first available
  // run config because the task has no default set — surfaced in the UI so
  // testers know which model the chains were generated against.
  let multi_turn_fallback_run_config_name: string | null = null

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
        signal: new_copilot_abort_signal(),
      })
      if (error || !data) {
        generation_error = "Failed to generate examples."
        return
      }
      single_turn_examples = data.examples_for_feedback ?? []
      sdg_session_config = data.sdg_session_config ?? null
      judge_info = data.judge_result ?? null
      await build_claims_for_review()
      if (claims_error) {
        generation_error = claims_error
        return
      }
      replace_step("review")
    } catch (e) {
      if (is_abort_error(e)) return
      generation_error = e instanceof Error ? e.message : "Generation failed."
    } finally {
      generation_loading = false
    }
  }

  // ── Step 4 multi-turn — drives real run_cases_batch SSE.
  //
  // Sequence:
  //   1. POST copilot/batch_plan → one scenario prompt per conversation;
  //      the user approves (edit/delete/regenerate) before anything runs.
  //   2. Pull the task's default run config → target_run_config for the
  //      drive loop. Multi-turn requires a KilnAgentRunConfig (the
  //      conversation needs an agent-shaped invoker).
  //   3. POST /multiturn_sdg/generate_cases with the approved prompts →
  //      one synthetic-user case per prompt (seed prompt + persona blob).
  //   4. POST /multiturn_sdg/run_cases_batch as SSE; consume the stream
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

  // The spec text driving generation — Step 3's refined description, falling
  // back to the Step 1 free text (same fallback the save path uses).
  function current_spec_text(): string {
    return (
      (refined_property_values.issue_description as string | null) ??
      description
    )
  }

  // Step 4 (multi-turn) part 1 — plan. Ask the batch planner for one
  // conversation scenario per case, balanced ~50/50 expected-pass /
  // expected-fail (the balance policy lives in multiturn_plan_guidance), then
  // pause on the approval screen. Nothing is driven until the user approves.
  async function on_plan_multi_turn() {
    generation_loading = true
    generation_error = null
    batch_plan = null
    batch_plan_edited = false
    multi_turn_chains = []
    multi_turn_progress = 0
    multi_turn_turns_done = 0
    multi_turn_batch_tag = null
    // Claims belong to the discarded plan's conversations — clear them so
    // browser Forward can't re-enter review over stale results.
    trace_claims = []
    trace_reviews = []
    driven_prompts_json = null
    multi_turn_phase = "planning"
    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan",
        {
          params: { path: { project_id, task_id } },
          body: {
            guidance: multiturn_plan_guidance(current_spec_text()),
            count: NUM_CASES,
          },
          signal: new_copilot_abort_signal(),
        },
      )
      if (error || !data) {
        generation_error = "Failed to plan the conversation batch."
        return
      }
      // Clamp: the planner is an LLM and can over-deliver or emit blanks;
      // both would 422 at drive time with no visible cause.
      const prompts = data.prompts
        .map((p) => p.trim())
        .filter(Boolean)
        .slice(0, NUM_CASES)
      if (prompts.length === 0) {
        generation_error = "The planner returned no usable scenarios — retry."
        return
      }
      batch_plan = { prompts, summary: data.summary }
    } catch (e) {
      if (is_abort_error(e)) return
      generation_error =
        e instanceof Error ? e.message : "Batch planning failed."
    } finally {
      generation_loading = false
    }
  }

  function on_delete_plan_prompt(index: number) {
    if (!batch_plan) return
    batch_plan = {
      ...batch_plan,
      prompts: batch_plan.prompts.filter((_, i) => i !== index),
    }
    batch_plan_edited = true
  }

  function on_edit_plan_prompt(index: number, value: string) {
    if (!batch_plan) return
    batch_plan = {
      ...batch_plan,
      prompts: batch_plan.prompts.map((p, i) => (i === index ? value : p)),
    }
    batch_plan_edited = true
  }

  // Step 4 (multi-turn) part 2 — drive from the approved plan. Each approved
  // scenario prompt becomes one synthetic-user case (case i ← prompt i via
  // generate_cases' case_prompts), then run_cases_batch drives one
  // conversation per case.
  async function on_drive_multi_turn() {
    if (!batch_plan || batch_plan.prompts.length === 0) {
      generation_error = "No approved plan — plan the batch first."
      return
    }
    const approved_prompts = batch_plan.prompts
    generation_loading = true
    generation_error = null
    multi_turn_progress = 0
    multi_turn_turns_done = 0
    multi_turn_chains = []
    multi_turn_batch_tag = null
    trace_claims = []
    trace_reviews = []
    driven_prompts_json = JSON.stringify(approved_prompts)
    multi_turn_phase = "generating_cases"

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
      const default_match = run_configs.find(
        (c) => c.id === task!.default_run_config_id,
      )
      const chosen_config = default_match ?? run_configs[0]
      multi_turn_fallback_run_config_name = default_match
        ? null
        : chosen_config.name
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

      // 2. Generate synthetic-user cases via copilot — one per approved
      // scenario prompt, so the driven batch is exactly the approved plan.
      multi_turn_phase = "generating_cases"
      const cases_resp = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases",
        {
          params: { path: { project_id, task_id } },
          body: {
            target_specification: current_spec_text(),
            num_cases: approved_prompts.length,
            case_prompts: approved_prompts,
          },
          signal: new_copilot_abort_signal(),
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
        signal: new_copilot_abort_signal(),
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
            multi_turn_batch_tag = event.batch_tag
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
            // One turn_completed == one assistant turn finished, across all
            // cases — drives the smooth progress indicator.
            multi_turn_turns_done += 1
          } else if (event.event === "case_completed") {
            multi_turn_chains = [
              ...multi_turn_chains,
              {
                case_index: event.case_index,
                persona_summary: `Case ${event.case_index + 1}`,
                total_cost: event.total_cost ?? 0,
                trace: traces_by_case[event.case_index] ?? [],
                leaf_run_id: event.leaf_run_id,
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

      // The drive is done but the judge + claim builder still run per trace —
      // surface that instead of sitting on a full progress bar.
      multi_turn_phase = "reviewing"
      await build_claims_for_review()
      if (claims_error) {
        generation_error = claims_error
        return
      }
      // Empty with no error = the user aborted (browser Back) — respect the
      // navigation instead of yanking them onto an empty review.
      if (trace_claims.length === 0) return
      // PUSH review (single-turn replaces): Back must return to the plan.
      goto_step("review")
    } catch (e) {
      if (is_abort_error(e)) return
      generation_error =
        e instanceof Error ? e.message : "Multi-turn generation failed."
    } finally {
      generation_loading = false
    }
  }

  function on_continue_from_generate_step() {
    if (is_multi_turn) {
      // No plan → plan. Chains driven but claims missing (judge/claims
      // failed or was aborted) → retry just that cheap stage, never the
      // whole drive. Otherwise → (re)drive the approved plan.
      if (batch_plan === null) {
        on_plan_multi_turn()
      } else if (multi_turn_chains.length > 0 && trace_claims.length === 0) {
        continue_to_review()
      } else {
        on_drive_multi_turn()
      }
    } else {
      on_generate_single_turn()
    }
  }

  // Advance from the Refine step (3) into Generate (4) and immediately kick
  // off generation — no extra click required. The in-step button only
  // surfaces if generation errored, as a retry affordance.
  function on_advance_to_generate() {
    goto_step("generate")
    // An existing plan renders for re-approval instead of auto-driving —
    // the spec may have changed since it was planned.
    if (is_multi_turn && batch_plan !== null) return
    on_continue_from_generate_step()
  }

  // Same pattern for Review (5) → Save (6): land on Save with the request
  // already in flight; only show the in-step button on error as retry.
  function on_advance_to_save() {
    goto_step("save")
    on_save()
  }

  // ── Step 5 state — Claim/Evidence review.
  // Generated traces are distilled into claims (per-trace server claim builder)
  // that the reviewer agrees/disagrees with; the trace stays hidden in a modal.
  let trace_claims: TraceClaims[] = []
  let trace_reviews: TraceReview[] = []
  let claims_loading = false
  let claims_error: string | null = null
  $: all_reviewed = all_traces_reviewed(trace_claims, trace_reviews)

  // Flatten the generated traces to the claim builder's (raw_input, raw_output)
  // shape. Multi-turn: first user message + the whole transcript as the output
  // (citations into "output" highlight within it), plus the structured trace so
  // the judge scores the real conversation. Single-turn: the I/O pair.
  function current_trace_ios(): {
    raw_input: string
    raw_output: string
    trace?: ChainTurn[]
    leaf_run_id?: string
  }[] {
    if (is_multi_turn) {
      return multi_turn_chains.map((c) => ({
        raw_input: c.trace.find((t) => t.role === "user")?.content ?? "",
        raw_output: c.trace.map((t) => `${t.role}: ${t.content}`).join("\n\n"),
        trace: c.trace,
        leaf_run_id: c.leaf_run_id,
      }))
    }
    return single_turn_examples.map((e) => ({
      raw_input: e.input,
      raw_output: e.output,
    }))
  }

  // SSE events from the eval_builder review_traces endpoint. The judge runs
  // server-side (local, in-app) via the Eval V2 llm_judge adapter; the claim
  // step calls the remote claim builder. We only consume these shapes.
  type ReviewTraceEvent =
    | { type: "batch_started"; total: number }
    | {
        type: "trace_reviewed"
        trace_index: number
        judge_score: string
        judge_reasoning: string
        claims: TraceClaims["claims"]
        final_judgement: TraceClaims["final_judgement"]
      }
    | { type: "trace_error"; trace_index: number; error: string }

  // Build claims for every generated trace via the studio-side review pipeline:
  // ONE call to review_traces, which fans out [judge → claim builder] per trace
  // (server-side, concurrency-capped) and streams a result per trace back.
  // Manual fetch + ReadableStream + SSE parsing — same pattern as run_cases_batch.
  async function build_claims_for_review() {
    claims_loading = true
    claims_error = null
    const eval_rubric =
      (refined_property_values.issue_description as string | null) ??
      description
    const ios = current_trace_ios()
    // judge_info comes from clarify_spec (single-turn). Multi-turn has none
    // until save, so fall back to the shared default judge — same as the save
    // path (build_default_judge_info).
    const judge = judge_info ?? build_default_judge_info(eval_rubric)
    // Fill by trace_index as events arrive (they complete out of order).
    const built: (TraceClaims | null)[] = new Array(ios.length).fill(null)
    try {
      const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval_builder/review_traces`
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          traces: ios,
          eval_rubric,
          judge: {
            prompt: judge.prompt,
            model_name: judge.task_metadata.model_name,
            model_provider: judge.task_metadata.model_provider_name,
          },
        }),
        signal: new_copilot_abort_signal(),
      })
      if (!response.ok || !response.body) {
        claims_error = `Failed to build claims (${response.status}).`
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const payload = line.slice(6).trim()
          if (!payload || payload === "complete") continue
          let event: ReviewTraceEvent
          try {
            event = JSON.parse(payload) as ReviewTraceEvent
          } catch {
            continue
          }
          if (event.type === "trace_reviewed") {
            const io = ios[event.trace_index]
            built[event.trace_index] = {
              trace_id: `trace_${event.trace_index}`,
              leaf_run_id: io.leaf_run_id ?? null,
              raw_input: io.raw_input,
              raw_output: io.raw_output,
              judge_score: event.judge_score,
              judge_reasoning: event.judge_reasoning,
              claims: event.claims ?? [],
              final_judgement: event.final_judgement,
            }
          } else if (event.type === "trace_error") {
            claims_error = `Failed to build claims for a trace: ${event.error}`
          }
        }
      }

      if (claims_error) return
      const complete = built.filter((t): t is TraceClaims => t !== null)
      trace_claims = complete
      trace_reviews = build_trace_reviews(complete)
    } catch (e) {
      if (is_abort_error(e)) return
      claims_error = e instanceof Error ? e.message : "Failed to build claims."
    } finally {
      claims_loading = false
    }
  }

  // Generation → review: build claims (unless already built) then advance.
  // Pushes (not replaces) so Back from review returns here — this path is
  // only reachable when Step 4 has real content to come back to.
  async function continue_to_review() {
    if (trace_claims.length === 0) {
      await build_claims_for_review()
      if (claims_error) return
      // Still empty with no error = aborted mid-build — stay put.
      if (trace_claims.length === 0) return
    }
    goto_step("review")
  }

  // ── Step 6 state — save
  let saving = false
  let save_error: string | null = null

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
      // Synthesize the judge_info locally rather than calling clarify_spec
      // (which runs full topic/input/output gen, takes 5-10 minutes).
      if (is_multi_turn) {
        if (multi_turn_batch_tag === null) {
          save_error =
            "No multi-turn chains were generated — go back to Step 4."
          return
        }
        const multi_turn_judge_info =
          build_default_judge_info(issue_description)
        // Carry the human's review through save: each reviewed trace maps to
        // its chain-leaf TaskRun (leaf_run_id from run_cases_batch); the
        // studio writes the golden rating + per-claim grades onto that leaf.
        const reviewed_chains = trace_claims
          .map((tc, i) => ({ tc, review: trace_reviews[i] }))
          // Truthy check: the batch runner emits "" (not null) when a leaf
          // has no id — such a chain can't be rated, so skip it.
          .filter(({ tc, review }) => tc.leaf_run_id && review)
          .map(({ tc, review }) => ({
            leaf_run_id: tc.leaf_run_id as string,
            user_says_meets_spec: user_says_meets_spec(tc, review),
            feedback: disagreement_feedback(review),
            claim_review: build_claim_review_payload(tc, review),
          }))
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
              judge_info: multi_turn_judge_info,
              multi_turn: {
                batch_tag: multi_turn_batch_tag,
                reviewed_chains,
              },
              task_description: "",
              task_prompt_with_example: task?.instruction ?? "",
            },
            signal: new_copilot_abort_signal(),
          },
        )
        if (error || !data) {
          save_error = "Save failed — try again."
          posthog.capture("eval_v2_save_error", {
            is_multi_turn: true,
            error_code: (error as { status?: number } | undefined)?.status,
          })
          return
        }
        posthog.capture("eval_v2_save_success", {
          is_multi_turn: true,
          num_cases: multi_turn_chains.length,
        })
        const saved = data as { id?: string }
        if (saved.id) {
          goto(`/specs/${project_id}/${task_id}/${saved.id}`)
        } else {
          replace_step("done")
        }
        return
      }

      // Single-turn save path.
      // Derive reviewed examples from the claim verdicts. The judge's verdict
      // anchors to final_judgement.expected_result (the server pins it to
      // judge_score deterministically); disagreeing with the final judgement
      // flips it, and disagreements' reasons become the feedback.
      const reviewed_examples: ReviewedExample[] = trace_claims.map((tc, i) => {
        const review = trace_reviews[i]
        return {
          input: tc.raw_input,
          output: tc.raw_output,
          model_says_meets_spec: tc.final_judgement.expected_result === "pass",
          user_says_meets_spec: user_says_meets_spec(tc, review),
          feedback: disagreement_feedback(review),
          claim_review: build_claim_review_payload(tc, review),
        }
      })

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
          signal: new_copilot_abort_signal(),
        },
      )
      if (error || !data) {
        save_error = "Save failed — try again."
        posthog.capture("eval_v2_save_error", {
          is_multi_turn: false,
          error_code: (error as { status?: number } | undefined)?.status,
        })
        return
      }
      posthog.capture("eval_v2_save_success", {
        is_multi_turn: false,
        num_cases: reviewed_examples.length,
      })
      // Land on the spec/eval detail page (titled "Eval: ..."). This is
      // the same destination v1 uses.
      const saved = data as { id?: string }
      if (saved.id) {
        goto(`/specs/${project_id}/${task_id}/${saved.id}`)
      } else {
        replace_step("done")
      }
    } catch (e) {
      if (is_abort_error(e)) return
      save_error = e instanceof Error ? e.message : "Save failed."
    } finally {
      saving = false
    }
  }

  // ── Navigation helpers
  function back_to_task() {
    goto(`/specs/${project_id}/${task_id}`)
  }

  // Escape hatch from Step 1 to the legacy manual builder (template carousel),
  // for users who'd rather author the eval themselves than use the assistant.
  function create_manually() {
    posthog.capture("eval_v2_create_manually_clicked")
    goto(`/specs/${project_id}/${task_id}/select_template`)
  }

  // Cmd/Ctrl-Enter fires the current step's primary action — but only the
  // steps with bespoke buttons. FormContainer-backed steps (clarify, single-
  // turn refine/review) already handle it; skipping them avoids double-firing.
  function handle_global_keydown(event: KeyboardEvent) {
    if (!((event.metaKey || event.ctrlKey) && event.key === "Enter")) return
    if (current_step === "describe") {
      if (description.trim() && !classifying) {
        event.preventDefault()
        classify_then_continue()
      }
    } else if (
      current_step === "refine" &&
      is_multi_turn &&
      !refined_preview_loading
    ) {
      if (
        name.trim() &&
        (refined_property_values.issue_description ?? "").trim()
      ) {
        event.preventDefault()
        on_refine_submit()
      }
    } else if (current_step === "review") {
      if (all_reviewed) {
        event.preventDefault()
        on_advance_to_save()
      }
    }
  }

  // Auto-load questions when entering Step 2
  $: if (current_step === "clarify" && !question_set && !questions_loading) {
    load_questions()
  }

  // Title + subtitle per step. Lifted to AppPage so the heading lives in
  // the standard page header, matching v1.
  function page_title_for(step: BuilderStep): string {
    switch (step) {
      case "describe":
        return "Create Eval"
      case "clarify":
        return "Clarify Eval"
      case "refine":
        return "Refine Eval"
      case "generate":
        return is_multi_turn ? "Generate Conversations" : "Generate Examples"
      case "review":
        return "Review Claims"
      case "save":
        return "Creating Eval"
      case "done":
        return "Eval Created"
    }
  }

  function page_subtitle_for(step: BuilderStep): string | undefined {
    switch (step) {
      case "describe":
        return "Describe a behaviour to enforce or avoid for your task. We'll structure it into a spec."
      case "clarify":
        return "Answer a few questions to reduce ambiguity in your eval."
      case "refine":
        return "Review and edit the refined spec before generating examples."
      case "generate":
        return is_multi_turn
          ? `Planning, then driving ${multi_turn_total} multi-turn conversations against your agent.`
          : "Generating sample inputs and outputs based on your spec."
      case "review":
        return "Agree or disagree with each claim. Open a [n] citation to see the trace."
      case "save":
        return "Persisting the spec, eval, and dataset."
      case "done":
        return undefined
    }
  }

  // v1 widens the layout when there's a side-by-side comparison or table
  // (review, refine-with-suggestions). Mirror that here so the typography
  // and form fields aren't crammed into a 3xl box on those steps.
  function page_max_w_for(step: BuilderStep): string {
    if (step === "review") return "max-w-[1400px]"
    if (step === "refine" && !is_multi_turn) return "max-w-[1400px]"
    // Multi-turn generate hosts the plan-approval table (long scenario
    // prompts) — give it the same wide layout as review.
    if (step === "generate" && is_multi_turn) return "max-w-[1400px]"
    return "max-w-[900px]"
  }

  $: page_title = page_title_for(current_step)
  $: page_subtitle = page_subtitle_for(current_step)
  $: page_max_w = page_max_w_for(current_step)

  // Total assistant turns expected across the whole batch — the denominator
  // for the smooth turn-level progress (cases run in parallel waves, so this
  // climbs steadily where the case count would sit still then jump).
  $: multi_turn_total_turns = multi_turn_total * TURNS_PER_CASE

  // Step 4 animation caption. Multi-turn shows turn-level progress while the
  // batch runs (smooth), then how many full conversations are ready.
  $: generate_animation_description = is_multi_turn
    ? multi_turn_phase === "planning"
      ? `Planning a balanced batch of ${NUM_CASES} conversation scenarios…`
      : multi_turn_phase === "generating_cases"
        ? `Generating ${multi_turn_total} synthetic-user cases from the approved plan…`
        : multi_turn_phase === "reviewing"
          ? `Judging ${multi_turn_chains.length} conversations and distilling claims for review…`
          : `Driving ${multi_turn_total} conversations — ${multi_turn_turns_done} of ${multi_turn_total_turns} turns (${multi_turn_progress} ready).`
    : "Kiln is generating example data to review and creating a judge. Hold tight!"

  // Multi-turn save tags existing chains rather than generating a dataset, so
  // the save copy differs from single-turn's generate-then-save.
  $: save_animation_description = is_multi_turn
    ? "Kiln is saving your eval and tagging the generated conversations. Hold tight!"
    : "Kiln is generating test and training data for your eval before saving. Hold tight!"
</script>

<svelte:window
  on:keydown={handle_global_keydown}
  on:beforeunload={handle_before_unload}
/>

<!-- Constrain AppPage (title + body) to page_max_w, matching v1 spec_builder.
     Centring v1's inner content is handled by AppPage's own header/slot
     layout, so no mx-auto here. -->
<div class={page_max_w}>
  <AppPage title={page_title} subtitle={page_subtitle} no_y_padding>
    {#if $kilnCopilotConnected === null}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if $kilnCopilotConnected === false}
      <CopilotRequiredCard
        title="Evals Builder"
        description_markdown="The new evals builder uses Kiln Copilot to generate cases and judges from a plain-text spec description."
        auth_href={`/specs/pro_auth?success_redirect_url=${encodeURIComponent(
          `/specs/${project_id}/${task_id}/builder`,
        )}`}
        connect_button_label="Connect Kiln Pro"
      />
    {:else}
      <div class="py-6">
        <!-- Step indicator -->
        <div class="text-sm text-gray-500 mb-6 flex items-center gap-2">
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
          <Warning warning_color="error" warning_message={task_error} />
        {:else if current_step === "describe"}
          <!-- ── Step 1 — Describe ── -->
          <FormElement
            label="What should this eval check?"
            description="Describe in plain language. We'll structure it for you."
            id="description"
            inputType="textarea"
            height="medium"
            bind:value={description}
            error_message={classify_error}
          />

          <div class="flex justify-between mt-8">
            <button class="btn btn-ghost btn-sm" on:click={back_to_task}
              >← Cancel</button
            >
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

          <div class="text-center mt-6 text-sm text-gray-500">
            Prefer to set it up yourself?
            <button
              class="link link-hover text-primary"
              on:click={create_manually}>Create manually</button
            >
          </div>
        {:else if current_step === "clarify"}
          <!-- ── Step 2 — Clarify (uses v1's Questions component) ── -->
          {#if questions_loading}
            <QuestioningAnimation
              title="Preparing Clarifying Questions"
              description="Kiln is analyzing your criteria to identify areas that could use more clarity. Hold tight!"
            />
          {:else if questions_error}
            <Warning warning_color="error" warning_message={questions_error} />
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
          {/if}
        {:else if current_step === "refine"}
          <!-- ── Step 3 — Refine ── -->
          {#if refined_preview_loading}
            <RefiningAnimation
              title="Refining Eval"
              description="Kiln is refining your eval with the feedback you provided. Hold tight!"
            />
          {:else if is_multi_turn}
            <!-- Multi-turn variant: examples fields don't apply (real examples
             come from Step 4 synthetic chains). Just name + description. -->
            <div class="mb-6">
              <FormElement
                label="Eval Name"
                description="A short name for your own reference (max 32 characters)."
                id="multi_turn_name"
                inputType="input"
                bind:value={name}
                validator={filename_string_short_validator}
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
                  Refinement: {suggested_edits.issue_description
                    .reason_for_edit}
                </div>
              {/if}
            </div>

            {#if not_incorporated_feedback}
              <Warning
                warning_color="primary"
                warning_icon="info"
                warning_message={`Unincorporated feedback: ${not_incorporated_feedback}`}
              />
            {/if}

            <div class="flex justify-end mt-8">
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
          {/if}
        {:else if current_step === "generate"}
          <!-- ── Step 4 — Generate ── -->
          {#if is_multi_turn && multi_turn_fallback_run_config_name}
            <Warning
              warning_color="primary"
              warning_icon="info"
              warning_message={`Using run config ${multi_turn_fallback_run_config_name} — set a default in task settings to silence this notice.`}
            />
          {/if}
          {#if generation_loading}
            <AnalyzingAnimation
              title={is_multi_turn
                ? multi_turn_phase === "planning"
                  ? "Planning Conversations"
                  : multi_turn_phase === "reviewing"
                    ? "Reviewing Conversations"
                    : "Generating Conversations"
                : "Analyzing Eval"}
              description={generate_animation_description}
              warning={is_multi_turn ? null : "This may take a while"}
            />
            {#if is_multi_turn && multi_turn_phase === "running_batch"}
              <!-- Turn-level bar: fills steadily as turns stream in, so the
                   parallel-but-wavy case completions don't read as stalled. -->
              <div class="max-w-md mx-auto mt-4">
                <progress
                  class="progress progress-primary w-full"
                  value={multi_turn_turns_done}
                  max={multi_turn_total_turns}
                ></progress>
              </div>
            {/if}
          {/if}

          {#if generation_error}
            <Warning warning_color="error" warning_message={generation_error} />
            <div class="text-center py-4 flex justify-center gap-2">
              {#if is_multi_turn && batch_plan !== null}
                <!-- Drive failed after approval — let the user rework the plan
                     instead of only retrying it verbatim. -->
                <button
                  class="btn"
                  on:click={() => {
                    generation_error = null
                  }}
                >
                  ← Back to plan
                </button>
              {/if}
              <button
                class="btn btn-primary"
                on:click={on_continue_from_generate_step}
              >
                Retry →
              </button>
            </div>
          {/if}

          {#if show_plan_approval && batch_plan}
            <!-- Plan approval: the batch runs only after the user approves
                 (optionally edited) scenario prompts. -->
            <BatchPlanApproval
              plan={batch_plan}
              summary_out_of_sync={batch_plan_edited}
              on_approve={on_drive_multi_turn}
              on_regenerate={on_plan_multi_turn}
              on_delete_prompt={on_delete_plan_prompt}
              on_edit_prompt={on_edit_plan_prompt}
              on_continue={multi_turn_chains.length > 0 &&
              driven_prompts_json === JSON.stringify(batch_plan.prompts)
                ? continue_to_review
                : null}
              on_back={() => history.back()}
            />
          {:else if !generation_loading && !generation_error}
            <div class="flex justify-end mt-8">
              {#if single_turn_examples.length > 0 || multi_turn_chains.length > 0}
                <!-- Generation already ran (navigated back into this step) —
                     continue to the existing results instead of re-running,
                     matching the browser Forward path. -->
                <button class="btn btn-primary" on:click={continue_to_review}>
                  Continue to review →
                </button>
              {:else}
                <!-- No results (a Back aborted generation) — offer to start it. -->
                <button
                  class="btn btn-primary"
                  on:click={on_continue_from_generate_step}
                >
                  <!-- Multi-turn only reaches this branch with no plan (a plan
                       renders the approval view above), so planning is always
                       the next action. -->
                  {is_multi_turn
                    ? "Plan conversations →"
                    : "Generate examples →"}
                </button>
              {/if}
            </div>
          {/if}
        {:else if current_step === "review"}
          <!-- ── Step 5 — Claim/Evidence review (trace hidden in a modal) ── -->
          {#if claims_loading}
            <AnalyzingAnimation
              title="Building claims"
              description="Distilling each trace into claims for you to review."
              warning={null}
            />
          {:else if claims_error}
            <Warning warning_color="error" warning_message={claims_error} />
          {:else}
            <ClaimEvidenceReview
              traces={trace_claims}
              bind:verdicts={trace_reviews}
              on_back={() => history.back()}
              on_save={on_advance_to_save}
              save_disabled={!all_reviewed}
              save_disabled_tooltip={all_reviewed
                ? null
                : "Give every trace an overall agree/disagree; disagreements need a reason."}
            />
          {/if}
        {:else if current_step === "save"}
          <!-- ── Step 6 — Save ── -->
          {#if saving}
            <SavingAnimation
              title="Creating Eval"
              description={save_animation_description}
            />
          {:else if save_error}
            <Warning warning_color="error" warning_message={save_error} />
            <div class="text-center py-4">
              <button class="btn btn-primary" on:click={on_save}>Retry →</button
              >
            </div>
          {/if}
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
    {/if}
  </AppPage>
</div>

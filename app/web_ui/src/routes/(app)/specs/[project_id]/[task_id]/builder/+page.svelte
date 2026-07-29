<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { agentInfo } from "$lib/agent"
  import {
    beforeNavigate,
    goto,
    pushState,
    replaceState,
  } from "$app/navigation"
  import { client, base_url } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"
  import { get_task_composite_id, load_task } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { indexedDBStore } from "$lib/stores/index_db_store"
  import { get, type Writable } from "svelte/store"
  // Draft persistence: the wizard's authoring state mirrors into IndexedDB
  // so navigation/reload can't destroy a session's work (SDG synth pattern).
  import {
    builder_draft_key,
    builder_mock_active,
    draft_has_content,
    restore_step,
    reusable_cached_cases,
    EMPTY_BUILDER_DRAFT,
    type BuilderDraft,
    type CachedSuCases,
    type SyntheticUserCaseWire,
  } from "./builder_draft"
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
  // Step 4 plan approval reuses the /generate batch-plan components — one
  // plan-review surface across the app rather than a builder-local fork.
  import KilnProBatchPlan from "../../../../generate/[project_id]/[task_id]/kiln_pro_batch_plan.svelte"
  import { multiturn_plan_guidance } from "./batch_plan_guidance"
  import {
    all_traces_reviewed,
    build_claim_review_payload,
    build_graded_traces,
    build_trace_reviews,
    disagreement_feedback,
    empty_claim_verdicts,
    is_trace_reviewed,
    review_target,
    reviewed_trace_count,
    select_review_subset,
    user_says_meets_spec,
    validate_refined_judge_prompt,
    type Claim,
    type FinalJudgement,
    type RefineJudgeProposal,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"
  // Step 4 plan-flow logic (stop banner, destructive-action confirms, the
  // preparing-review gate's resolved counting) — pure and unit-tested.
  import {
    dominant_failure_message,
    drive_stop_banner,
    driven_data_confirm,
    first_preflight_failure,
    new_plan_confirm,
    resolved_selected_count,
    type DriveStop,
    type PreflightFailure,
    type PreflightLane,
  } from "./plan_flow"
  // Reuse v1's themed loading animations on the wizard's transition screens
  // instead of bare dot-spinners, so the two builders feel consistent.
  import QuestioningAnimation from "$lib/ui/animations/questioning_animation.svelte"
  import RefiningAnimation from "$lib/ui/animations/refining_animation.svelte"
  import AnalyzingAnimation from "$lib/ui/animations/analyzing_animation.svelte"
  import SavingAnimation from "$lib/ui/animations/saving_animation.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import type { SuggestedEdit } from "../spec_utils"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { filename_string_short_validator } from "$lib/utils/input_validators"
  import { sse_data_payloads } from "$lib/utils/sse"
  import {
    build_default_judge_info,
    judge_config_from_sdg_step,
    type JudgeConfig,
  } from "$lib/eval/default_judge"
  import {
    kilnCopilotConnected,
    initCopilotConnectionStore,
  } from "$lib/stores/copilot_connection_store"
  import CopilotRequiredCard from "$lib/ui/kiln_copilot/copilot_required_card.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type {
    Task,
    ModelProviderName,
    QuestionSet,
    QuestionWithAnswer,
    SpecType,
    SubsampleBatchOutputItemApi,
    SyntheticDataGenerationSessionConfigApi,
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
  // data is lost — instead of leaving the builder. popstate then restores
  // the correct step. The step is just a value in history.state, not a
  // per-step route, so this survives any future change to the set of steps.
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
    // Navigating away also cancels the preparing-review gate's ownership of
    // the advance: in-flight claim builds keep running (they belong to the
    // traces, not the screen), but the gate must not push the user into
    // review from another step. Continue re-enters it, resolving instantly
    // when everything already built.
    preparing_review = false
    claims_gate_error = null
    current_step = step
  }
  $: sync_step_from_history(
    ($page.state as { builder_step?: BuilderStep }).builder_step,
  )

  // Warn before a full reload/close/external-nav when there's unsaved work —
  // history can't guard a real unload (mirrors v1's warn_before_unload). SPA
  // transitions (the save redirect) don't trigger beforeunload, so a successful
  // save won't spuriously prompt.
  //
  // With draft persistence the authoring state (spec fields, approved plan)
  // survives navigation, so the guards protect only what a draft can't
  // restore: the clarify answers, driven results and review progress, and
  // work in flight. Under the dev mock nothing persists, so everything
  // counts as unpersisted.
  $: has_unpersisted_work =
    current_step === "clarify" ||
    trace_claims.length > 0 ||
    single_turn_examples.length > 0 ||
    generation_loading ||
    preparing_review ||
    saving ||
    !draft_ready
  $: warn_before_unload =
    current_step !== "describe" &&
    current_step !== "done" &&
    has_unpersisted_work
  function handle_before_unload(event: BeforeUnloadEvent) {
    if (!warn_before_unload) return
    event.preventDefault()
    event.returnValue = ""
  }

  // beforeunload never fires for in-app SPA navigation (sidebar, deeplinks),
  // which unmounts the wizard and loses all component-local state just the
  // same — guard those too. In-wizard steps use shallow routing
  // (pushState/replaceState), which doesn't run beforeNavigate, so step
  // Back/Forward stays free; this fires only when the ROUTE changes.
  // The save-success redirect suppresses it: the work is persisted.
  let leave_guard_suppressed = false
  beforeNavigate((nav) => {
    if (leave_guard_suppressed || !warn_before_unload) return
    // "leave" = real unload (reload/close) — the beforeunload handler owns
    // that path and cancel() can't stop it anyway.
    if (nav.type === "leave") return
    if (
      !confirm(
        "Leave the eval builder? Your answers, generated data, and review progress here will be lost.",
      )
    ) {
      nav.cancel()
    }
  })

  // ── Draft persistence (builder_draft.ts). The mirror below rewrites the
  // draft on every change to a persisted field; onMount restores it silently
  // to the furthest safe step (never past the plan screen, never review).
  // The batch tags ride along as a correctness carry: they name chains on
  // disk, and without them a lost session would orphan those chains forever
  // (delete-on-next-drive would never learn about them).
  let draft_ready = false
  let draft_store: Writable<BuilderDraft> | null = null
  let persist_draft: () => Promise<void> = () => Promise.resolve()

  // Reactive mirror: referencing every persisted field makes any change to
  // one rewrite the draft (the store's subscriber writes IndexedDB async).
  // draft_ready guards the pre-restore window — mirroring the initial empty
  // state would wipe the saved draft — and stays false under the mock.
  $: if (draft_ready && draft_store) {
    draft_store.set({
      description,
      spec_type,
      name,
      property_values,
      refined_property_values,
      suggested_edits,
      not_incorporated_feedback,
      batch_plan,
      batch_plan_edited,
      cached_su_cases,
      multi_turn_batch_tag,
      undeleted_batch_tags,
    })
  }

  // Restore silently — no resume prompt. The three-tier destructive-action
  // confirms (New Batch Plan etc.) are the reset escape hatch, so a stale
  // draft never traps the user.
  async function restore_draft() {
    const { store, initialized, persist } = indexedDBStore(
      builder_draft_key(project_id, task_id),
      EMPTY_BUILDER_DRAFT,
    )
    await initialized
    draft_store = store
    persist_draft = persist
    const saved = get(store)
    if (draft_has_content(saved)) {
      description = saved.description
      spec_type = saved.spec_type
      name = saved.name
      // An empty stored record keeps the var's seeded default (e.g.
      // property_values starts with the issue keys) instead of erasing it.
      if (Object.keys(saved.property_values).length > 0) {
        property_values = saved.property_values
      }
      refined_property_values = saved.refined_property_values
      suggested_edits = saved.suggested_edits
      not_incorporated_feedback = saved.not_incorporated_feedback
      batch_plan = saved.batch_plan
      batch_plan_edited = saved.batch_plan_edited
      cached_su_cases = saved.cached_su_cases ?? null
      multi_turn_batch_tag = saved.multi_turn_batch_tag
      undeleted_batch_tags = saved.undeleted_batch_tags
      // Rebuild the shallow-routing chain up to the restored step (the
      // mount already seeded "describe") so the browser's Back walks the
      // wizard steps exactly as in the original session instead of
      // immediately leaving the builder.
      const step = restore_step(saved)
      if (step === "refine" || step === "generate") {
        goto_step("refine")
      }
      if (step === "generate") {
        goto_step("generate")
      }
    }
    draft_ready = true
  }

  // Clear the draft once the save persisted (the leave-guard hook point):
  // stop the mirror FIRST so the wizard's still-populated state can't
  // rewrite the draft after the wipe, then flush — the store's subscriber
  // writes async, and navigating before the write lands would resurrect
  // the draft on the next visit.
  async function clear_builder_draft() {
    draft_ready = false
    draft_store?.set(EMPTY_BUILDER_DRAFT)
    try {
      await persist_draft()
    } catch (e) {
      console.error("Failed to clear the builder draft:", e)
    }
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
      // Restore the saved draft after the task loads (a task error skips
      // it), and never under the dev mock: canned mock state must not
      // persist into a real draft, nor a real draft restore into a mock
      // session — the mock leaves draft_ready false, so the mirror never
      // writes either.
      if (!builder_mock_active()) {
        await restore_draft()
      }
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
  // Defaulting to "issue" keeps the refine + save shapes valid even when
  // classification fails or is unavailable.
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
  // to a spec_type + suggested name + structured property_values. On error
  // we keep the "issue" defaults so the user can still proceed and fill in
  // property_values via the Q&A / Refine steps.
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
  // Non-blocking: refinement failing still lands the user on an editable
  // refine step, but they should know their answers weren't incorporated.
  let refine_warning: string | null = null

  // Called by Questions component on Continue. Fires the refinement call and
  // populates the state shape consumed by RefineSpec. Matches v1's flow:
  //   answer Qs → refining spinner → refine screen with editable suggestions.
  async function on_continue_from_clarify(
    questions_and_answers: QuestionWithAnswer[],
  ) {
    goto_step("refine")
    refined_preview_loading = true
    refine_warning = null
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
      if (error || !data) {
        refine_warning = `Couldn't refine the spec from your answers (${createKilnError(
          error,
        ).getMessage()}) — edit it directly below.`
        return
      }

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
    } catch (e) {
      if (is_abort_error(e)) return
      // Refinement is optional — the user lands on an editable refine step
      // either way — but the failure must not be silent.
      refine_warning =
        "Couldn't refine the spec from your answers — edit it directly below."
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
  // The judge, in the ONE JudgeConfig shape used by review and save alike.
  // Single-turn: mapped from clarify_spec's judge_result. Multi-turn: none
  // until review builds the default.
  let judge_info: JudgeConfig | null = null
  // The judge the review step actually ran — save persists THIS object, so
  // the judge the user calibrated against is the judge that ships.
  let review_judge: JudgeConfig | null = null
  // Identity snapshot of what the review judged (spec name + spec text).
  // Save is refused when it no longer matches: renaming or editing the spec
  // after review would ship a judge the review never calibrated.
  let reviewed_identity: string | null = null

  // Number of synthetic-user cases to drive in one multi-turn batch —
  // matches NUM_CASES_MAX in libs/core/kiln_ai/synthetic_user/runner.py.
  const NUM_CASES = 40
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
  // The plan's generated synthetic users, reused on a re-drive while the
  // plan and spec are byte-unchanged: SU cases don't depend on the run
  // config, so a fix-config-then-drive-again loop shouldn't re-pay the
  // multi-minute generation. Rides the persisted draft.
  let cached_su_cases: CachedSuCases | null = null
  // Approved plan length drives the batch size; NUM_CASES is the requested
  // plan size before any deletions.
  $: multi_turn_total = batch_plan?.prompts.length ?? NUM_CASES
  // Which loading stage Step 4 is in — drives the progress screen only.
  // The interactive plan-approval view is DERIVED (show_plan_approval below),
  // not a phase, so no code path can strand it behind a stale flag.
  type MultiTurnPhase =
    | "idle"
    | "preflight"
    | "planning"
    | "generating_cases"
    | "running_pipeline"
  let multi_turn_phase: MultiTurnPhase = "idle"
  $: pipeline_running =
    generation_loading && multi_turn_phase === "running_pipeline"
  $: show_plan_approval =
    is_multi_turn &&
    batch_plan !== null &&
    !generation_loading &&
    !generation_error &&
    // The preparing-review gate owns the screen between drive and review.
    !preparing_review &&
    claims_gate_error === null
  // Live pipeline counters, reset at each drive. Latest completed-turn count
  // per case (the stream's turns_completed is per-case cumulative, so a
  // re-delivered event can't double-count a turn); counting turns makes
  // steady progress visible where a case-only count would sit still then
  // jump — cases complete in concurrency-limited waves.
  let turns_by_case: Record<number, number> = {}
  let judged_case_count = 0
  let pipeline_failed_count = 0
  $: multi_turn_turns_done = Object.values(turns_by_case).reduce(
    (n, t) => n + t,
    0,
  )
  function reset_pipeline_counters() {
    turns_by_case = {}
    judged_case_count = 0
    pipeline_failed_count = 0
    case_failure_messages = []
  }

  // The cases whose conversations were actually driven (chains exist on
  // disk). Save mints one EvalInput per driven case — the eval slice the
  // runner re-drives per run config.
  let driven_cases: SyntheticUserCaseWire[] = []
  // batch_tag from the pipeline's batch_started event — passed to the save
  // endpoint so the backend can tag the matching chains for the eval
  // dataset.
  let multi_turn_batch_tag: string | null = null
  // Every batch that put chains on disk and hasn't been cleaned up yet —
  // aborted re-drives can strand several. The next drive passes ALL of them
  // as replace_batch_tags so none is orphaned (delete-on-redrive).
  let undeleted_batch_tags: string[] = []
  // Cases actually driven this run (salvage can make it smaller than the
  // plan) — the denominator for pipeline progress.
  let pipeline_total_cases = 0
  // Unified stop screen: set when a drive ends short of the approved plan
  // (post-retry case failures or upstream salvage drops). The plan screen
  // stops ONCE with an informational banner and the recovery actions —
  // Continue with the survivors (iff any) or Drive again. No failure is
  // shown without an action, and no failure silently shrinks the batch;
  // all-failed is the same screen with Continue naturally absent.
  let drive_stop: DriveStop | null = null
  // Per-case failure messages from the last drive's case_failed frames —
  // aggregated into the stop banner's "most common" diagnosis.
  let case_failure_messages: string[] = []
  // The run config the drive ran with — named in the stop banner so a
  // config-class failure is diagnosable without leaving the wizard. The
  // model rides along for the abort banner (the model IS the usual culprit).
  let drive_run_config_name: string | null = null
  let drive_run_config_model: string | null = null
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
      judge_info = data.judge_result
        ? judge_config_from_sdg_step(data.judge_result)
        : null
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

  // ── Step 4 multi-turn — one review_pipeline SSE stream.
  //
  // Sequence:
  //   1. POST copilot/batch_plan → one scenario prompt per conversation;
  //      the user approves (edit/delete/regenerate) before anything runs.
  //   2. Pull the task's default run config and send its ID — the server
  //      drives the task with the saved config verbatim (model, prompt,
  //      sampling, tools). Multi-turn requires a KilnAgentRunConfig (the
  //      conversation needs an agent-shaped invoker).
  //   3. Preflight the three model lanes (target config, SU driver, judge)
  //      with one-word completions — a dead key/model stops the drive
  //      before any spend instead of after the SU-gen minutes.
  //   4. POST /multiturn_sdg/generate_cases with the approved prompts →
  //      ONE batch call, one synthetic-user case per prompt.
  //   5. POST /eval_builder/review_pipeline as SSE; the server runs
  //      [drive → judge → claims] per case and the PipelineEvent frames
  //      drive the per-row status pills + the review results.
  //
  // The synthetic-user driver model is fixed rather than user-selectable;
  // making it selectable would go in the UI here.
  const SU_DRIVER_DEFAULT = {
    model_name: "claude_4_5_haiku",
    model_provider: "openrouter",
  } as const
  const TURNS_PER_CASE = 5

  // Events on the merged review-pipeline stream (one stream runs
  // [drive → judge → claims] per case; see eval_builder_api.review_pipeline).
  // All eval_builder frames share the `type` discriminator and the
  // {code, message} error shape.
  type PipelineEvent =
    | { type: "batch_started"; batch_tag: string; total_cases: number }
    | {
        type: "turn_completed"
        case_index: number
        turns_completed: number
        total_turns: number
      }
    | { type: "case_driven"; case_index: number; leaf_run_id: string }
    | {
        type: "case_judged"
        case_index: number
        leaf_run_id: string
        raw_input: string
        raw_output: string
        judge_score: TraceClaims["judge_score"]
        judge_reasoning: string
        total_cost: number
      }
    | {
        type: "case_failed"
        case_index: number
        stage: "drive" | "judge"
        code: string
        message: string
      }
    | {
        type: "batch_completed"
        judged: number
        failed: number
        batch_tag: string
        total_cost: number
      }
    | { type: "batch_failed"; code: string; message: string }
    | { type: "batch_aborted"; error: string; stage: "drive" | "judge" }

  // THE spec text — the single source every consumer reads (batch planning,
  // synthetic-user generation, the default judge prompt, and the saved Spec),
  // so no two stages can see different text. Step 3's refined values win;
  // property_values covers a skipped refine; Step 1's free text is the floor.
  function spec_text(): string {
    const values =
      Object.keys(refined_property_values).length > 0
        ? refined_property_values
        : property_values
    return (values.issue_description as string | null) ?? description
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
    // The cached synthetic users belong to the discarded plan (the byte
    // compare would reject them anyway) — drop the payload from the draft.
    cached_su_cases = null
    reset_pipeline_counters()
    drive_stop = null
    // Deliberately NOT clearing multi_turn_batch_tag (save still needs it)
    // or undeleted_batch_tags: the next drive passes the cleanup list as
    // replace_batch_tags, and the server deletes those batches once the new
    // drive has produced replacement chains.
    // Claims belong to the discarded plan's conversations — clear them so
    // browser Forward can't re-enter review over stale results.
    trace_claims = []
    trace_reviews = []
    selected_trace_indices = []
    driven_prompts_json = null
    multi_turn_phase = "planning"
    try {
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan",
        {
          params: { path: { project_id, task_id } },
          body: {
            guidance: multiturn_plan_guidance(spec_text()),
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

  // Driven results worth guarding: the exact current plan has judged
  // conversations behind it. True both on the accepted has-data screen and
  // on the failure stop screen with survivors.
  $: has_driven_results =
    trace_claims.length > 0 &&
    batch_plan !== null &&
    driven_prompts_json === JSON.stringify(batch_plan.prompts)
  // Accepted has-data state (clean drive, or survivors accepted via
  // Continue): Drive is hidden — Continue to Review is the only forward
  // action. On the stop screen Drive stays visible as the re-drive
  // recovery.
  $: has_data_accepted = has_driven_results && drive_stop === null
  // How many cases the last drive was asked to run — the denominator for
  // the has-data notice (survivors vs. the approved plan at drive time).
  $: driven_plan_size = driven_prompts_json
    ? (JSON.parse(driven_prompts_json) as string[]).length
    : 0

  // Clears the driven results (conversations, review progress, stop banner)
  // so the plan screen returns to its pre-drive editable form. Batch tags
  // are deliberately kept — the next drive passes them as replace_batch_tags
  // so the chains on disk are cleaned up then.
  function discard_driven_results() {
    trace_claims = []
    trace_reviews = []
    selected_trace_indices = []
    driven_prompts_json = null
    drive_stop = null
    reset_pipeline_counters()
  }

  function on_delete_plan_prompt(index: number) {
    if (!batch_plan) return
    // Deleting a row from a plan with driven results discards those results
    // (the plan no longer matches what ran) — confirm at the destructive
    // click. A pristine or merely-edited plan deletes rows freely, matching
    // SDG's unconfirmed row deletes.
    if (has_driven_results) {
      const msg = driven_data_confirm(
        "Editing the plan",
        trace_claims.length,
        // Review progress exists only once the user accepted the results
        // (was in review) — on the stop screen no review exists yet.
        drive_stop === null,
      )
      if (!confirm(msg)) return
      discard_driven_results()
    }
    batch_plan = {
      ...batch_plan,
      prompts: batch_plan.prompts.filter((_, i) => i !== index),
    }
    batch_plan_edited = true
  }

  // New Batch Plan ALWAYS confirms — a plan alone costs minutes to make
  // (SDG's New Batch Plan routes through its destructive-back confirm too).
  function on_new_plan_with_confirm() {
    const msg = new_plan_confirm({
      has_driven_results,
      survivors: trace_claims.length,
      include_review_progress: drive_stop === null,
      plan_edited: batch_plan_edited,
    })
    if (!confirm(msg)) return
    on_plan_multi_turn()
  }

  // Step 4 (multi-turn) part 2 — drive from the approved plan. The approved
  // prompts become synthetic-user cases in ONE batch call (case i ← prompt i
  // via generate_cases' case_prompts), then a single review_pipeline stream
  // runs [drive → judge → claims] per case — each case flows through
  // independently, so the plan rows light up as their case progresses.
  // Ping every lane concurrently (~2s total); the returned failure is the
  // first in blame order, not race order. Each lane costs about a token —
  // nothing next to the batch spend a dead lane would waste.
  async function preflight_lanes(
    lanes: {
      lane: PreflightLane
      model_name: string
      model_provider: string
    }[],
    signal: AbortSignal,
  ): Promise<PreflightFailure | null> {
    const outcomes = await Promise.all(
      lanes.map(async (l) => {
        const model = `${l.model_name} via ${l.model_provider}`
        const { error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/eval_builder/preflight_model",
          {
            params: { path: { project_id, task_id } },
            body: {
              model_name: l.model_name,
              // JudgeConfig carries the provider as a plain string; the
              // route 422s on a value outside the enum.
              model_provider: l.model_provider as ModelProviderName,
            },
            signal,
          },
        )
        if (error) {
          return {
            lane: l.lane,
            ok: false,
            message: createKilnError(error).getMessage(),
            model,
          }
        }
        return { lane: l.lane, ok: true }
      }),
    )
    return first_preflight_failure(outcomes)
  }

  async function on_drive_multi_turn() {
    if (!batch_plan || batch_plan.prompts.length === 0) {
      generation_error = "No approved plan — plan the batch first."
      return
    }
    const approved_prompts = batch_plan.prompts
    generation_loading = true
    generation_error = null
    multi_turn_phase = "preflight"

    try {
      // 1. Resolve target_run_config: prefer the task's default; if none
      // set, fall back to the first available run config so the user
      // doesn't have to detour into task settings just to try v2. Only
      // error when the task has zero configs (genuinely unrunnable).
      // Re-fetch the task first: the default run config can change while
      // the wizard is open — the stop banner's own recovery loop sends
      // the user to /run in another tab to fix it — and driving with the
      // mount-time snapshot would resolve the OLD default.
      task = await load_task(project_id, task_id)
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
      drive_run_config_name = chosen_config.name
      const rcp = chosen_config.run_config_properties
      if (!isKilnAgentRunConfig(rcp)) {
        generation_error =
          "Multi-turn requires a Kiln Agent run config; the selected one isn't."
        return
      }
      drive_run_config_model = rcp.model_name
      if (!chosen_config.id) {
        generation_error = "The selected run config has no id."
        return
      }
      // Reference the saved config by id: the server drives the task with it
      // verbatim, so model, prompt, sampling, and TOOLS all match a manual run.
      const target_run_config_id = chosen_config.id

      // 2. The judge, resolved BEFORE the pipeline (not just before the
      // stream) so the preflight below covers the judge lane too — the
      // judge-dies-after-drives case is the expensive one.
      const judge = judge_info ?? build_default_judge_info(spec_text())

      // 3. Preflight ALL THREE lanes concurrently before anything runs or
      // is discarded: a dead key/model stops the drive here — before the
      // SU-gen minutes and the batch's model spend — on the same stop
      // screen, with the previous drive's results (if any) left intact.
      // Validates key/billing/model resolution only, not tools/MCP or
      // mid-run rate limits.
      const preflight_failure = await preflight_lanes(
        [
          {
            lane: "run config",
            model_name: rcp.model_name,
            model_provider: rcp.model_provider_name,
          },
          {
            lane: "synthetic-user driver",
            model_name: SU_DRIVER_DEFAULT.model_name,
            model_provider: SU_DRIVER_DEFAULT.model_provider,
          },
          {
            lane: "judge",
            model_name: judge.model_name,
            model_provider: judge.model_provider,
          },
        ],
        new_copilot_abort_signal(),
      )
      if (preflight_failure) {
        drive_stop = {
          survivors: trace_claims.length,
          failed: 0,
          dominant_error: null,
          preflight: preflight_failure,
        }
        return
      }

      // 4. Preflight passed — commit to the drive. Every undeleted previous
      // batch is superseded from here: the pipeline deletes their chains
      // once this drive has produced replacements.
      const previous_batch_tag = multi_turn_batch_tag
      const previous_driven_cases = driven_cases
      const tags_to_replace = [...undeleted_batch_tags]
      drive_stop = null
      trace_claims = []
      trace_reviews = []
      selected_trace_indices = []
      driven_cases = []
      driven_prompts_json = JSON.stringify(approved_prompts)
      pipeline_total_cases = approved_prompts.length
      reset_pipeline_counters()

      // 5. The synthetic-user cases. Their generation depends only on the
      // plan and the spec — never the run config — so a re-drive with both
      // byte-unchanged (the fix-config-then-drive-again recovery loop)
      // reuses the cached cases instead of re-paying the multi-minute
      // copilot call. Any plan edit or New Batch Plan misses the cache.
      let cases = reusable_cached_cases(
        cached_su_cases,
        approved_prompts,
        spec_text(),
      )
      if (cases) {
        posthog.capture("eval_v2_su_cases_reused", {
          num_cases: cases.length,
        })
      } else {
        // Generate via copilot — ONE batch call, one case per approved
        // scenario prompt. Under the upstream salvage contract a flaky case
        // is dropped instead of failing the batch; scenario_index maps each
        // survivor back to its plan row.
        multi_turn_phase = "generating_cases"
        const cases_resp = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/multiturn_sdg/generate_cases",
          {
            params: { path: { project_id, task_id } },
            body: {
              target_specification: spec_text(),
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
        cases = cases_resp.data.cases as SyntheticUserCaseWire[]
        cached_su_cases = {
          prompts_json: JSON.stringify(approved_prompts),
          spec_text: spec_text(),
          cases,
        }
      }
      // Salvage can drop cases upstream: the driven count (the progress
      // denominator) is what actually came back, not the plan size.
      pipeline_total_cases = cases.length

      // 6. Remember the judge (the ONE JudgeConfig shape used by review and
      // save alike, resolved at step 2) and identity BEFORE the pipeline
      // runs so save can verify nothing changed under the results.
      review_judge = judge
      reviewed_identity = JSON.stringify({ name, spec: spec_text() })

      // 7. One SSE stream runs the whole pipeline: [drive → judge → claims]
      // per case. POST endpoint, so fetch + shared SSE reader (EventSource
      // is GET-only).
      multi_turn_phase = "running_pipeline"
      const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval_builder/review_pipeline`
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          cases,
          turns: TURNS_PER_CASE,
          target_run_config_id,
          su_driver: SU_DRIVER_DEFAULT,
          replace_batch_tags: tags_to_replace,
          spec_name: name,
          judge,
        }),
        signal: new_copilot_abort_signal(),
      })

      if (!response.ok || !response.body) {
        let detail: string
        try {
          const err_json = await response.json()
          // The error handler wraps detail as {message}; typed route errors
          // nest {code, message} inside it — unwrap either shape.
          const message = err_json?.message
          detail =
            (typeof message === "string" ? message : message?.message) ??
            err_json?.detail?.message ??
            "unknown"
        } catch {
          detail = await response.text().catch(() => "unknown")
        }
        generation_error = `review_pipeline failed (${response.status}): ${detail}`
        return
      }

      // Fill by case_index as case_reviewed events arrive (cases complete
      // out of order); compacted into trace_claims at batch end.
      const built: (TraceClaims | null)[] = new Array(cases.length).fill(null)
      let any_case_driven = false
      // Set by a batch_aborted frame: a config-scoped judge failure aborted
      // the batch server-side. Cases judged before it remain valid.
      let batch_abort: { error: string; stage: string } | null = null
      const reader = response.body.getReader()
      stream_loop: for await (const payload of sse_data_payloads(reader)) {
        if (payload === "complete") break
        let event: PipelineEvent
        try {
          event = JSON.parse(payload) as PipelineEvent
        } catch {
          continue
        }

        if (event.type === "batch_started") {
          multi_turn_batch_tag = event.batch_tag
        } else if (event.type === "turn_completed") {
          turns_by_case = {
            ...turns_by_case,
            [event.case_index]: event.turns_completed,
          }
        } else if (event.type === "case_driven") {
          any_case_driven = true
          // This case's conversation exists on disk — it belongs in the
          // saved eval slice even if a later stage (judge/claims) fails.
          driven_cases = [...driven_cases, cases[event.case_index]]
          // Chains exist on disk under this batch's tag from here on —
          // record it immediately so an abort can't orphan the batch.
          if (
            multi_turn_batch_tag &&
            !undeleted_batch_tags.includes(multi_turn_batch_tag)
          ) {
            undeleted_batch_tags = [
              ...undeleted_batch_tags,
              multi_turn_batch_tag,
            ]
          }
        } else if (event.type === "case_judged") {
          // Claims stay unbuilt here — they're built lazily (build_claims)
          // for the traces the review selection surfaces or the user opens.
          built[event.case_index] = {
            trace_id: `case_${event.case_index}`,
            leaf_run_id: event.leaf_run_id || null,
            raw_input: event.raw_input,
            raw_output: event.raw_output,
            judge_score: event.judge_score,
            judge_reasoning: event.judge_reasoning,
            claims: null,
            final_judgement: null,
            claims_state: "unbuilt",
            claims_error: null,
          }
          judged_case_count += 1
        } else if (event.type === "case_failed") {
          pipeline_failed_count += 1
          // Keep the message: the stop banner aggregates these into the
          // dominant-error diagnosis.
          case_failure_messages.push(event.message)
          posthog.capture("eval_v2_pipeline_case_failed", {
            stage: event.stage,
            code: event.code,
          })
        } else if (event.type === "batch_failed") {
          posthog.capture("eval_v2_pipeline_batch_failed", {
            code: event.code,
          })
          generation_error = `The pipeline failed: ${event.message}`
          break stream_loop
        } else if (event.type === "batch_aborted") {
          posthog.capture("eval_v2_pipeline_batch_aborted", {
            stage: event.stage,
          })
          // Keep draining: results that raced past the abort frame are
          // still valid survivors; the server ends the stream right after.
          batch_abort = { error: event.error, stage: event.stage }
        }
        // batch_completed carries totals the rows already reflect; the
        // `complete` terminator ends the loop.
      }
      if (any_case_driven) {
        if (!batch_abort) {
          // The server deleted the superseded batches once replacements
          // existed — drop them from the cleanup list.
          undeleted_batch_tags = undeleted_batch_tags.filter(
            (t) => !tags_to_replace.includes(t),
          )
        }
        // On an abort the deletion may never have run (the drive was torn
        // down mid-flight) — keep the tags. Delete-on-next-drive is
        // idempotent, so re-passing an already-deleted tag is harmless.
      } else {
        // Nothing was driven: no replacement chains, no deletions — keep
        // pointing at the previous batch (and its cases) so save/cleanup
        // still work.
        multi_turn_batch_tag = previous_batch_tag
        driven_cases = previous_driven_cases
      }

      // Compact survivors BEFORE any error/warning path: completed verdicts
      // are paid results and must never be discarded by a late failure.
      const complete = built.filter((t): t is TraceClaims => t !== null)
      if (complete.length > 0) {
        trace_claims = complete
        trace_reviews = build_trace_reviews(complete)
        // The review subset is decided the moment all verdicts are in —
        // deterministic and judge-stratified, so both classes calibrate.
        selected_trace_indices = select_review_subset(complete)
      }
      if (generation_error) return
      if (batch_abort) {
        // The server aborted the whole batch on a config-scoped judge
        // failure — the same stop screen, reached in seconds, with the
        // abort diagnosis leading the banner.
        drive_stop = {
          survivors: complete.length,
          failed: approved_prompts.length - complete.length,
          dominant_error: null,
          aborted_error: batch_abort.error,
        }
        return
      }
      // Failures reaching here are TERMINAL — transient errors were already
      // retried by the drive runner. A clean batch auto-advances silently;
      // ANY shortfall vs the approved plan stops once on the plan screen
      // with the outcome and the recovery choice (continue with survivors /
      // re-drive) — informed consent instead of silent shrinkage.
      const failed = approved_prompts.length - complete.length
      if (failed > 0) {
        drive_stop = {
          survivors: complete.length,
          failed,
          dominant_error: dominant_failure_message(case_failure_messages),
        }
        return
      }
      // Clean batch: hold the progress screen while the selected traces'
      // claims build, then advance to a fully-loaded review.
      start_claims_gate()
    } catch (e) {
      if (is_abort_error(e)) return
      generation_error =
        e instanceof Error ? e.message : "Multi-turn generation failed."
    } finally {
      generation_loading = false
    }
  }

  // Accepting the survivors from the stop screen: from here the normal
  // has-data rules apply (Drive hidden; destructive actions confirm with
  // the review-progress clause).
  function on_continue_with_survivors() {
    drive_stop = null
    continue_to_review()
  }

  function on_continue_from_generate_step() {
    if (is_multi_turn) {
      // No plan → plan; otherwise (re)drive the approved plan. A re-drive
      // passes the previous batch_tag so its chains are deleted server-side.
      if (batch_plan === null) {
        on_plan_multi_turn()
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
  // Which traces the reviewer is asked to review (indices into trace_claims):
  // a judge-stratified subset for multi-turn batches, everything for
  // single-turn. A default, not a cap — unselected traces stay reviewable.
  let selected_trace_indices: number[] = []
  let claims_loading = false
  let claims_error: string | null = null
  $: all_reviewed = all_traces_reviewed(trace_claims, trace_reviews)
  // Multi-turn save gate: the human-rated golden answer key caps at 25% of
  // chains server-side, so the reviewer must rate at least N//4 traces —
  // reviewing more is welcome, fewer starves the answer key.
  $: multi_turn_review_target = review_target(trace_claims.length)
  $: reviewed_count = reviewed_trace_count(trace_claims, trace_reviews)
  $: save_gate_met = is_multi_turn
    ? trace_claims.length > 0 && reviewed_count >= multi_turn_review_target
    : all_reviewed

  // ── Lazy claims (multi-turn). The pipeline stream stops at the judge;
  // only traces the review surfaces (the selected subset) or the user opens
  // pay the remote claim-builder round trip.
  const CLAIMS_BUILD_CONCURRENCY = 5

  // Guarded patch: a re-drive replaces trace_claims while builds are in
  // flight — the trace_id check stops a stale response landing on the new
  // batch's trace at the same index.
  function patch_trace_claims(
    index: number,
    trace_id: string,
    patch: Partial<TraceClaims>,
  ) {
    const current = trace_claims[index]
    if (!current || current.trace_id !== trace_id) return
    trace_claims = trace_claims.map((t, i) =>
      i === index ? { ...t, ...patch } : t,
    )
  }

  // Outcome feeds the preparing-review gate: "config_error" (auth-class
  // HTTP failure — dead copilot key etc.) means every remaining build would
  // fail identically, so the gate cancels its queue instead of opening a
  // review full of dead cards.
  type ClaimsBuildOutcome = "built" | "error" | "config_error" | "skipped"

  async function build_claims_for_index(
    index: number,
  ): Promise<ClaimsBuildOutcome> {
    const tc = trace_claims[index]
    const judge = review_judge
    if (!tc || !judge) return "skipped"
    // "error" and "unbuilt" both proceed — re-opening an errored trace is
    // the retry affordance.
    if (tc.claims_state === "built" || tc.claims_state === "building")
      return "skipped"
    const trace_id = tc.trace_id
    patch_trace_claims(index, trace_id, {
      claims_state: "building",
      claims_error: null,
    })
    try {
      const { data, error, response } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/build_claims",
        {
          params: { path: { project_id, task_id } },
          // The rubric under test is the judge's actual prompt — the claim
          // builder pressure-tests the rubric the verdict was produced under.
          // No abort signal: builds belong to the trace (identity-checked in
          // patch_trace_claims), not to whichever screen is showing.
          body: {
            raw_input: tc.raw_input,
            raw_output: tc.raw_output,
            eval_rubric: judge.prompt,
            judge_score: tc.judge_score,
            judge_reasoning: tc.judge_reasoning,
          },
        },
      )
      if (error || !data) {
        patch_trace_claims(index, trace_id, {
          claims_state: "error",
          claims_error: createKilnError(error).getMessage(),
        })
        return response?.status === 401 || response?.status === 403
          ? "config_error"
          : "error"
      }
      const claims = (data.claims ?? []) as Claim[]
      patch_trace_claims(index, trace_id, {
        claims,
        final_judgement: data.final_judgement as FinalJudgement,
        claims_state: "built",
        claims_error: null,
      })
      // Size the positional verdict slots now that the claim list exists.
      trace_reviews = trace_reviews.map((r, i) =>
        i === index && r.claim_verdicts.length !== claims.length
          ? { ...r, claim_verdicts: empty_claim_verdicts(claims) }
          : r,
      )
      return "built"
    } catch (e) {
      patch_trace_claims(index, trace_id, {
        claims_state: "error",
        claims_error:
          e instanceof Error ? e.message : "Failed to build claims.",
      })
      return "error"
    }
  }

  // Build claims for the selected subset with a small worker pool.
  // include_errored re-enqueues errored traces — the gate's Retry path
  // (normally an errored build resolves as-is and keeps its in-review
  // retry card).
  function prefetch_selected_claims(include_errored = false) {
    const queue = selected_trace_indices.filter((i) => {
      const s = trace_claims[i]?.claims_state
      return s === "unbuilt" || (include_errored && s === "error")
    })
    const workers = Math.min(CLAIMS_BUILD_CONCURRENCY, queue.length)
    for (let w = 0; w < workers; w++) {
      void (async () => {
        while (queue.length > 0) {
          const next = queue.shift()
          if (next === undefined) break
          const outcome = await build_claims_for_index(next)
          if (outcome === "config_error" && preparing_review) {
            // Auth-class failure (dead copilot key etc.): every remaining
            // build would fail identically — cancel the queue and stop the
            // gate with ONE error + Retry instead of opening a review full
            // of dead cards.
            queue.length = 0
            claims_gate_error = `Couldn't build the review claims: ${
              trace_claims[next]?.claims_error ?? "authorization failed"
            }`
            preparing_review = false
          }
        }
      })()
    }
  }

  // ── The preparing-review gate (multi-turn). After the drive (or after
  // accepting survivors), hold the Step 4 progress screen while the worker
  // pool builds claims for the stratified selection, and advance only once
  // EVERY selected trace is RESOLVED — built or errored. Review then opens
  // fully loaded: navigation is non-linear (dots jump anywhere), so only
  // wait-for-all removes loading states from review entirely. Errored
  // builds don't hold the door — they keep their in-review error+retry
  // card.
  let preparing_review = false
  let claims_gate_error: string | null = null
  // Gate start time for the claims-build duration telemetry event.
  let claims_gate_started_ms = 0

  function start_claims_gate(include_errored = false) {
    claims_gate_error = null
    preparing_review = true
    claims_gate_started_ms = Date.now()
    prefetch_selected_claims(include_errored)
  }

  $: selected_claims_resolved = resolved_selected_count(
    trace_claims,
    selected_trace_indices,
  )
  $: if (
    preparing_review &&
    current_step === "generate" &&
    claims_gate_error === null &&
    selected_trace_indices.length > 0 &&
    selected_claims_resolved === selected_trace_indices.length
  ) {
    preparing_review = false
    posthog.capture("eval_v2_claims_build_completed", {
      duration_ms: Date.now() - claims_gate_started_ms,
      num_selected: selected_trace_indices.length,
      num_errored: selected_trace_indices.filter(
        (i) => trace_claims[i]?.claims_state === "error",
      ).length,
    })
    // PUSH review (single-turn replaces): Back must return to the plan.
    goto_step("review")
  }

  // The review component reports the trace it's showing (also its retry
  // affordance) — build that trace's claims if they aren't underway.
  function on_open_trace(index: number) {
    void build_claims_for_index(index)
  }

  // ── Under-the-hood judge refinement (Step 6, at save). The reviewer aligns
  // on CLAIMS, never on prompt text — so refinement is invisible: if their
  // grades carry any disagreement, the judge prompt is refined from those
  // grades and the REFINED judge is what ships. Non-blocking — any failure or
  // an unusable refined prompt keeps the original judge, so a refine hiccup
  // never blocks the save.
  async function refined_judge_for_save(
    judge: JudgeConfig,
  ): Promise<JudgeConfig> {
    const graded_traces = build_graded_traces(trace_claims, trace_reviews)
    const has_disagreement = graded_traces.some(
      (t) =>
        t.final_judgement.human_grade === "disagree" ||
        t.claims.some((c) => c.human_grade === "disagree"),
    )
    if (!has_disagreement) return judge
    const { data, error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/eval_builder/refine_judge",
      {
        params: { path: { project_id, task_id } },
        body: { judge_prompt: judge.prompt, graded_traces },
        signal: new_copilot_abort_signal(),
      },
    )
    // Refine failed — ship the original judge rather than block the save.
    // The fallback is invisible to the user by design, so leave a telemetry
    // trail: silent fallbacks would otherwise read as "refinement works".
    if (error || !data) {
      console.warn(
        "Judge refinement failed at save; keeping the reviewed judge.",
        error,
      )
      posthog.capture("eval_v2_judge_refine_fallback", {
        reason: "request_failed",
      })
      return judge
    }
    const proposal = data as RefineJudgeProposal
    // Only ship a mechanically-valid refined prompt (it renders into the judge
    // harness verbatim); otherwise fall back to the original.
    const validation_error = validate_refined_judge_prompt(
      proposal.refined_judge_prompt,
    )
    if (validation_error) {
      console.warn(
        `Refined judge prompt rejected (${validation_error}); keeping the reviewed judge.`,
      )
      posthog.capture("eval_v2_judge_refine_fallback", {
        reason: "invalid_refined_prompt",
      })
      return judge
    }
    return { ...judge, prompt: proposal.refined_judge_prompt }
  }

  // SSE events from the eval_builder review_traces endpoint (single-turn).
  // The judge runs server-side (local, in-app) via the Eval V2 llm_judge
  // adapter; the claim step calls the remote claim builder.
  type ReviewTraceEvent =
    | { type: "batch_started"; total: number }
    | {
        type: "trace_reviewed"
        trace_index: number
        // The exact text the claim builder saw — the UI displays and
        // resolves citations against these.
        raw_input: string
        raw_output: string
        judge_score: TraceClaims["judge_score"]
        judge_reasoning: string
        claims: TraceClaims["claims"]
        final_judgement: TraceClaims["final_judgement"]
      }
    | {
        type: "trace_error"
        trace_index: number
        code: string
        message: string
      }

  // Build claims for every SINGLE-TURN example via review_traces, which fans
  // out [judge → claim builder] per trace (server-side, concurrency-capped)
  // and streams a result per trace back. Multi-turn never comes here — its
  // claims arrive on the merged review_pipeline stream during the drive.
  async function build_claims_for_review() {
    claims_loading = true
    claims_error = null
    const ios = single_turn_examples.map((e) => ({
      raw_input: e.input,
      raw_output: e.output,
    }))
    // judge_info comes from clarify_spec; fall back to the shared default.
    // Either way, remember the judge the review ran — save persists that
    // exact object.
    const judge = judge_info ?? build_default_judge_info(spec_text())
    review_judge = judge
    reviewed_identity = JSON.stringify({ name, spec: spec_text() })
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
        // spec_name pins the review judge's score identity to the one the
        // saved eval will use; the judge's prompt doubles as the claim
        // builder's rubric server-side.
        body: JSON.stringify({
          traces: ios,
          spec_name: name,
          judge,
        }),
        signal: new_copilot_abort_signal(),
      })
      if (!response.ok || !response.body) {
        claims_error = `Failed to build claims (${response.status}).`
        return
      }

      const reader = response.body.getReader()
      for await (const payload of sse_data_payloads(reader)) {
        if (payload === "complete") continue
        let event: ReviewTraceEvent
        try {
          event = JSON.parse(payload) as ReviewTraceEvent
        } catch {
          continue
        }
        if (event.type === "trace_reviewed") {
          built[event.trace_index] = {
            trace_id: `trace_${event.trace_index}`,
            leaf_run_id: null,
            raw_input: event.raw_input,
            raw_output: event.raw_output,
            judge_score: event.judge_score,
            judge_reasoning: event.judge_reasoning,
            claims: event.claims ?? [],
            final_judgement: event.final_judgement,
            claims_state: "built",
            claims_error: null,
          }
        } else if (event.type === "trace_error") {
          posthog.capture("eval_v2_review_trace_error", { code: event.code })
          claims_error = `Failed to build claims for a trace: ${event.message}`
        }
      }

      if (claims_error) return
      const complete = built.filter((t): t is TraceClaims => t !== null)
      trace_claims = complete
      trace_reviews = build_trace_reviews(complete)
      // Single-turn reviews everything: clarify_spec already subsampled the
      // most informative examples upstream.
      selected_trace_indices = complete.map((_, i) => i)
    } catch (e) {
      if (is_abort_error(e)) return
      claims_error = e instanceof Error ? e.message : "Failed to build claims."
    } finally {
      claims_loading = false
    }
  }

  // Generation → review: advance to existing results, rebuilding when stale.
  // Pushes (not replaces) so Back from review returns here — this path is
  // only reachable when Step 4 has real content to come back to.
  async function continue_to_review() {
    // Results reviewed under an old name/spec text are stale — the judge
    // identity changed, so the review must be re-run, not presented.
    const stale =
      trace_claims.length > 0 &&
      reviewed_identity !== JSON.stringify({ name, spec: spec_text() })
    if (stale) {
      trace_claims = []
      trace_reviews = []
      selected_trace_indices = []
      if (is_multi_turn) {
        // Multi-turn results come from the merged pipeline (judge rides the
        // drive), so a stale review means re-driving the plan.
        generation_error =
          "The eval's name or description changed since the review — drive the conversations again."
        return
      }
    }
    if (trace_claims.length === 0) {
      if (is_multi_turn) {
        // Nothing to show (a Back aborted the pipeline) — re-drive.
        on_drive_multi_turn()
        return
      }
      await build_claims_for_review()
      if (claims_error) return
      // Still empty with no error = aborted mid-build — stay put.
      if (trace_claims.length === 0) return
    }
    if (is_multi_turn) {
      // Multi-turn claims are lazy — gate the advance on the selected
      // subset being fully resolved (instant when already built).
      start_claims_gate()
      return
    }
    // Single-turn claims were built eagerly with the examples — advance.
    goto_step("review")
  }

  // ── Step 6 state — save
  let saving = false
  let save_error: string | null = null

  async function on_save() {
    saving = true
    save_error = null
    try {
      if (reviewed_identity !== JSON.stringify({ name, spec: spec_text() })) {
        save_error =
          "The eval's name or description changed since the review — go back and re-run the review."
        return
      }
      // Source of truth for the saved spec is refined_property_values —
      // populated from Step 1 description initially, then updated in Step 3
      // via v1's RefineSpec component when the user accepts/edits the LLM's
      // proposed refinements. Fall back to property_values if Step 3 was
      // skipped (no refinements were proposed). spec_text() applies the same
      // precedence, so the saved definition equals what generation/review saw.
      const final_values =
        Object.keys(refined_property_values).length > 0
          ? refined_property_values
          : property_values
      const issue_description = spec_text()
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

      // The judge to persist = the judge the review ran (review_judge). The
      // fallback only fires if save is somehow reached without a review.
      const review_judge_config =
        review_judge ?? judge_info ?? build_default_judge_info(spec_text())
      // Under the hood: if the reviewer disagreed anywhere, refine the judge
      // from their grades so the shipped judge incorporates their feedback.
      // Falls back to the reviewed judge on any refine failure (never blocks
      // the save).
      const save_judge = await refined_judge_for_save(review_judge_config)

      // Multi-turn save: golden/train tags land on the driven chains; the
      // eval slice is minted server-side as EvalInputs from the driven cases.
      if (is_multi_turn) {
        if (multi_turn_batch_tag === null || driven_cases.length === 0) {
          save_error =
            "No multi-turn chains were generated — go back to Step 4."
          return
        }
        // Carry the human's review through save: each reviewed trace maps to
        // its chain-leaf TaskRun (leaf_run_id from run_cases_batch); the
        // studio writes the golden rating + per-claim grades onto that leaf.
        // Only traces the human actually reviewed ride along (subset review:
        // unreviewed chains land in the train split, unrated).
        const reviewed_chains = trace_claims
          .map((tc, i) => ({ tc, review: trace_reviews[i] }))
          // Truthy check: the batch runner emits "" (not null) when a leaf
          // has no id — such a chain can't be rated, so skip it.
          .filter(
            ({ tc, review }) =>
              tc.leaf_run_id && review && is_trace_reviewed(tc, review),
          )
          .map(({ tc, review }) => ({
            leaf_run_id: tc.leaf_run_id as string,
            user_says_meets_spec: user_says_meets_spec(tc, review),
            feedback: disagreement_feedback(review),
            // A trace can be reviewed on the blind verdict alone when its
            // claims build failed — the rating stands, the grades don't.
            claim_review:
              tc.claims_state === "built"
                ? build_claim_review_payload(tc, review)
                : null,
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
              judge_info: save_judge,
              multi_turn: {
                batch_tag: multi_turn_batch_tag,
                reviewed_chains,
                cases: driven_cases,
                // The drive settings this wizard's conversations ran with
                // ride onto the Eval, so eval-time re-drives replay the same
                // synthetic user (model + turns).
                drive_config: {
                  model_name: SU_DRIVER_DEFAULT.model_name,
                  model_provider: SU_DRIVER_DEFAULT.model_provider,
                  turns: TURNS_PER_CASE,
                },
              },
              task_prompt_with_example: task?.instruction ?? "",
            },
            signal: new_copilot_abort_signal(),
          },
        )
        if (error || !data) {
          save_error = createKilnError(error).getMessage()
          posthog.capture("eval_v2_save_error", {
            is_multi_turn: true,
            error_code: (error as { status?: number } | undefined)?.status,
          })
          return
        }
        posthog.capture("eval_v2_save_success", {
          is_multi_turn: true,
          num_cases: trace_claims.length,
        })
        const saved = data as { id?: string }
        // Persisted — the leave guard has nothing left to protect, and the
        // draft's job is done (a kept draft would restore a stale wizard
        // over the saved eval on the next visit).
        await clear_builder_draft()
        if (saved.id) {
          leave_guard_suppressed = true
          goto(`/specs/${project_id}/${task_id}/${saved.id}`)
        } else {
          replace_step("done")
        }
        return
      }

      // Single-turn save path.
      // Derive reviewed examples from the claim verdicts. The judge's verdict
      // anchors to judge_score (the server pins final_judgement.
      // expected_result to it deterministically); disagreeing with the final
      // judgement flips it, and disagreements' reasons become the feedback.
      const reviewed_examples: ReviewedExample[] = trace_claims.map((tc, i) => {
        const review = trace_reviews[i]
        return {
          input: tc.raw_input,
          output: tc.raw_output,
          model_says_meets_spec: tc.judge_score === "pass",
          user_says_meets_spec: user_says_meets_spec(tc, review),
          feedback: disagreement_feedback(review),
          claim_review: build_claim_review_payload(tc, review),
        }
      })

      if (!sdg_session_config) {
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
            judge_info: save_judge,
            sdg_session_config,
            task_prompt_with_example: task?.instruction ?? "",
          },
          signal: new_copilot_abort_signal(),
        },
      )
      if (error || !data) {
        save_error = createKilnError(error).getMessage()
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
      // Persisted — the leave guard has nothing left to protect, and the
      // draft's job is done (a kept draft would restore a stale wizard
      // over the saved eval on the next visit).
      await clear_builder_draft()
      if (saved.id) {
        leave_guard_suppressed = true
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
      if (save_gate_met) {
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
        return is_multi_turn
          ? `Reviewing ${multi_turn_review_target} of ${trace_claims.length} conversations — a judge-balanced sample. Agree or disagree with each claim; open a [n] citation to see the trace.`
          : "Agree or disagree with each claim. Open a [n] citation to see the trace."
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
  // climbs steadily where the case count would sit still then jump). Uses
  // the DRIVEN case count: salvage can drive fewer cases than the plan has.
  $: multi_turn_total_turns = pipeline_total_cases * TURNS_PER_CASE

  // Step 4 animation caption for the pre-pipeline loading stages (plan and
  // SU generation); the pipeline stage has its own progress screen below.
  $: generate_animation_description = is_multi_turn
    ? multi_turn_phase === "planning"
      ? `Planning a balanced batch of ${NUM_CASES} synthetic-user scenarios…`
      : multi_turn_phase === "preflight"
        ? "Checking that your run config, synthetic-user driver, and judge respond before driving…"
        : `Creating ${multi_turn_total} synthetic users from the approved plan…`
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
          {:else}
            {#if refine_warning}
              <div class="mb-4">
                <Warning
                  warning_color="warning"
                  warning_message={refine_warning}
                />
              </div>
            {/if}
            {#if is_multi_turn}
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
          {#if generation_loading && !pipeline_running}
            <!-- Plan and SU generation are each one long request (minutes at
                 a 40-case batch) — the standard animation warning line sets
                 the expectation, matching every other long wait in the app. -->
            <AnalyzingAnimation
              title={is_multi_turn
                ? multi_turn_phase === "planning"
                  ? "Planning Batch"
                  : multi_turn_phase === "preflight"
                    ? "Checking Configuration"
                    : "Creating Synthetic Users"
                : "Analyzing Eval"}
              description={generate_animation_description}
              warning={is_multi_turn && multi_turn_phase !== "preflight"
                ? "This may take a while, depending on the number of scenarios"
                : is_multi_turn
                  ? null
                  : "This may take a while"}
            />
          {/if}
          {#if pipeline_running}
            <!-- The drive stage: the standard loading animation plus the
                 house batch-progress readout (slim bar + tiny count line,
                 mirroring /generate's batch generation). The bar tracks
                 TURNS for smooth motion (cases complete in concurrency
                 waves), so the count line LEADS with turns — the number
                 that moves with the bar — then the conversation outcome. -->
            <AnalyzingAnimation
              title="Driving Conversations"
              description="Kiln is driving and judging each conversation against your agent. Hold tight!"
              warning={null}
            />
            <div class="flex flex-col items-center mt-2">
              <progress
                class="progress w-56 progress-success"
                value={multi_turn_turns_done}
                max={multi_turn_total_turns}
              ></progress>
              <div class="font-light text-xs text-center mt-1">
                {multi_turn_turns_done} of {multi_turn_total_turns} turns, {judged_case_count}
                of {pipeline_total_cases} conversations complete{#if pipeline_failed_count > 0},
                  {pipeline_failed_count} failed{/if}
              </div>
            </div>
          {/if}
          {#if preparing_review}
            <!-- The claims gate: the progress screen holds while the
                 selected traces' claims build, so review opens fully
                 loaded — no spinners behind any dot. -->
            <AnalyzingAnimation
              title="Preparing Review"
              description="Kiln is distilling each conversation into claims for you to review. Hold tight!"
              warning={null}
            />
            <div class="flex flex-col items-center mt-2">
              <progress
                class="progress w-56 progress-success"
                value={selected_claims_resolved}
                max={selected_trace_indices.length}
              ></progress>
              <div class="font-light text-xs text-center mt-1">
                Preparing review — {selected_claims_resolved} of {selected_trace_indices.length}
                ready
              </div>
            </div>
          {/if}
          {#if claims_gate_error}
            <!-- Config-class build failure — same error+retry surface as
                 the wizard's other loading stages. -->
            <Warning
              warning_color="error"
              warning_message={claims_gate_error}
            />
            <div class="text-center py-4 flex justify-center gap-2">
              <button
                class="btn"
                on:click={() => {
                  claims_gate_error = null
                }}
              >
                ← Back to plan
              </button>
              <button
                class="btn btn-primary"
                on:click={() => start_claims_gate(true)}
              >
                Retry →
              </button>
            </div>
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
            {#if drive_stop}
              <!-- The unified stop banner: partial failure warns, all-failed
                   errors — same surface, message and actions scale with what
                   happened. trusted+markdown for the in-message /run
                   deeplink (renders target=_blank, wizard state survives). -->
              <div class="mb-4">
                <Warning
                  warning_color={drive_stop.survivors > 0 &&
                  !drive_stop.aborted_error &&
                  !drive_stop.preflight
                    ? "warning"
                    : "error"}
                  markdown
                  trusted
                  warning_message={drive_stop_banner(
                    drive_stop,
                    drive_run_config_name,
                    drive_run_config_model,
                  )}
                />
              </div>
            {/if}
            <!-- Plan approval: the batch runs only after the user approves
                 the scenario prompts — the shared /generate batch-plan
                 surface (delete rows or regenerate; per-row editing rides
                 the shared component's affordances). -->
            <KilnProBatchPlan
              plan={batch_plan}
              summary_out_of_sync={batch_plan_edited}
              on_generate_inputs={on_drive_multi_turn}
              on_regenerate={on_new_plan_with_confirm}
              on_delete_prompt={on_delete_plan_prompt}
              hide_generate_button={has_data_accepted}
              generate_button_label={`Drive ${batch_plan.prompts.length} Conversation${
                batch_plan.prompts.length === 1 ? "" : "s"
              }`}
            />
            <!-- Wizard chrome stays outside the shared component: it has
                 no slots, and /generate has no back/continue concept.
                 Back never confirms — confirms live on destructive actions,
                 not navigation (review state embeds human grading work). -->
            <div class="flex flex-row justify-between mt-4">
              <button
                class="btn btn-ghost btn-sm"
                on:click={() => history.back()}
              >
                ← Back
              </button>
              {#if has_driven_results}
                <!-- Conversations were already driven from this exact plan —
                     returning to the results doesn't re-spend model calls.
                     Also the survivors path from the stop banner. -->
                <div class="flex flex-row items-center gap-3">
                  <span class="font-light text-xs text-gray-500">
                    {#if trace_claims.length < driven_plan_size}
                      {trace_claims.length} of {driven_plan_size} conversations completed
                    {:else}
                      {trace_claims.length} conversations driven
                    {/if}
                  </span>
                  <button
                    class="btn btn-sm btn-primary"
                    on:click={on_continue_with_survivors}
                  >
                    Continue to Review →
                  </button>
                </div>
              {/if}
            </div>
          {:else if !generation_loading && !generation_error && !preparing_review && !claims_gate_error}
            <div class="flex justify-end mt-8">
              {#if single_turn_examples.length > 0 || trace_claims.length > 0}
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
          {:else if trace_claims.length === 0}
            <!-- Browser Forward can land here after results were cleared
                 (plan regenerated / drive restarted) — offer the way back
                 instead of an empty review. -->
            <Warning
              warning_color="warning"
              warning_message="There are no reviewed conversations — generate them first."
            />
            <div class="text-center py-4">
              <button class="btn btn-primary" on:click={() => history.back()}>
                ← Back
              </button>
            </div>
          {:else}
            <ClaimEvidenceReview
              traces={trace_claims}
              bind:verdicts={trace_reviews}
              selected_indices={selected_trace_indices}
              judged_noun={is_multi_turn ? "conversation" : "example"}
              {on_open_trace}
              on_back={() => history.back()}
              on_save={on_advance_to_save}
              save_disabled={!save_gate_met}
              save_disabled_tooltip={save_gate_met
                ? null
                : is_multi_turn
                  ? `Review ${
                      multi_turn_review_target === 1
                        ? "the conversation"
                        : `all ${multi_turn_review_target} conversations`
                    } to continue. Your ratings teach the eval what correct looks like, and your reasons for disagreeing help improve the judge.`
                  : "Review every example to continue. If you disagree, add a short reason so we can improve the judge."}
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

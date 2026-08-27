<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount, onDestroy } from "svelte"
  import { agentInfo } from "$lib/agent"
  import {
    afterNavigate,
    beforeNavigate,
    goto,
    pushState,
    replaceState,
  } from "$app/navigation"
  import { client, base_url } from "$lib/api_client"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import AvailableModelsDropdown from "$lib/ui/run_config_component/available_models_dropdown.svelte"
  import { build_suggested_models } from "$lib/ui/run_config_component/suggested_models"
  import {
    available_models,
    get_task_composite_id,
    load_available_models,
    load_task,
    provider_name_from_id,
  } from "$lib/stores"
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
    draft_after_save_keeping_stranded_tags,
    draft_has_content,
    questions_are_current,
    reset_draft_keeping_tags,
    restore_step,
    reusable_cached_cases,
    reusable_minted_inputs,
    should_invalidate_refined_values,
    should_prefill_suggested_name,
    EMPTY_BUILDER_DRAFT,
    type BuilderDraft,
    type CachedMintedInputs,
    type CachedSuCases,
    type SyntheticUserCaseWire,
  } from "./builder_draft"
  import { isKilnAgentRunConfig } from "$lib/types"
  // Reuse v1 spec_builder's Questions component so the clarify screen looks
  // identical across builders. When v1 evolves, v2 follows for free.
  import Questions from "../spec_builder/questions.svelte"
  // Claim/Evidence replaces the read-the-trace pass/fail review: the reviewer
  // agrees/disagrees with distilled claims; the trace stays hidden in a modal.
  import ClaimEvidenceReview from "./claim_evidence_review.svelte"
  // Multi-turn Step 4 is plan-first: the batch planner drafts one scenario
  // per conversation for approval before any conversation is driven.
  // Step 4 plan approval reuses the /generate batch-plan components — one
  // plan-review surface across the app rather than a builder-local fork.
  import KilnProBatchPlan from "../../../../generate/[project_id]/[task_id]/kiln_pro_batch_plan.svelte"
  import {
    grounding_data_guide,
    multiturn_plan_guidance,
    single_turn_plan_guidance,
  } from "./batch_plan_guidance"
  // Dataset grounding (single-turn): auto-pick a real task run to anchor the
  // planner's and input generator's sense of what an input looks like.
  import {
    fetch_task_sample_candidates,
    is_five_star_rated,
    type TaskSampleExample,
  } from "$lib/utils/task_sample_example"
  import {
    apply_rejudge_results,
    build_claim_review_payload,
    build_graded_traces,
    build_trace_reviews,
    calibration_gate_target,
    disagreed_trace_indices,
    disagreement_feedback,
    empty_claim_verdicts,
    flipped_indices,
    grade_disagreement_count,
    has_grade_disagreement,
    is_trace_reviewed,
    plan_save_action,
    refine_judge_tooltip,
    rejudge_shortfall_notice,
    review_cta,
    review_target,
    reviewed_trace_count,
    select_calibration_subset,
    select_review_subset,
    user_says_meets_spec,
    validate_refined_judge_prompt,
    type Claim,
    type FinalJudgement,
    type RefineJudgeProposal,
    type RejudgeCaseResult,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"
  // Step 4 plan-flow logic (stop banner, destructive-action confirms, the
  // preparing-review gate's resolved counting) — pure and unit-tested.
  import {
    compact_batch_slots,
    dominant_failure_message,
    drive_lanes_unchanged,
    drive_stop_banner,
    driven_data_confirm,
    first_preflight_failure,
    new_plan_confirm,
    plan_drive,
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
  // Conversation-themed loading animation (chat bubbles building a thread)
  // for the MULTI-TURN generation and review-prep screens, which are about
  // building conversations; the single-turn arm renders the analysis
  // animation on the same screens.
  import ConversationAnimation from "$lib/ui/animations/conversation_animation.svelte"
  import { spec_field_configs } from "../select_template/spec_templates"
  import type { SuggestedEdit } from "../spec_utils"
  // Splits the refine response into edits the form can show and edits it
  // cannot; the latter are discarded (the request does not declare those
  // fields) and reported for telemetry.
  import {
    keep_rendered_fields,
    split_refine_edits,
    type ProposedSpecEdit,
  } from "./refine_fields"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { filename_string_short_validator } from "$lib/utils/input_validators"
  // The wizard hand-rolls its action rows, so it renders FormContainer's
  // keyboard hint itself — same platform check the shared container uses.
  import { isMacOS } from "$lib/utils/platform"
  import { sse_data_payloads } from "$lib/utils/sse"
  import { with_deadline } from "$lib/utils/deadline_signal"
  import {
    model_choice,
    type JudgeConfig,
    type ModelChoice,
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
  //   refine    — Step 3: eval name + description with proposed refinements
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
  // The user makes five stops; saving is a transition, not a step.
  const TOTAL_STEPS = 5
  const STEP_INDEX: Record<BuilderStep, number> = {
    describe: 1,
    clarify: 2,
    refine: 3,
    generate: 4,
    review: 5,
    save: 5,
    done: 5,
  }

  // AbortController for in-flight Copilot requests. Mirrors v1 spec_builder:
  // starting a new request implicitly cancels any prior one (no stale
  // responses overwriting newer state), and browser Back (via popstate)
  // calls abort_copilot_request() so stepping out of a loading step also
  // kills the request instead of leaving it running in the background.
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

  // Deadline on the judge-copilot calls (authoring and the loop's refine):
  // one full server attempt. The server retries for up to ~20 minutes for
  // callers that can afford to wait; an interactive flow cannot, so past this
  // the call is surfaced as failed — authoring as a retryable drive error,
  // refine as the inline error under the review actions.
  const JUDGE_COPILOT_DEADLINE_MS = 300_000

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
  //                  loading steps (save) don't become Back targets. Both
  //                  arms' generate step holds the interactive plan-approval
  //                  view, so review is PUSHED over it instead.
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
    // review from another step. Next re-enters it, resolving instantly
    // when everything already built.
    preparing_review = false
    claims_gate_error = null
    // Same for a calibration round in flight: the abort above cancelled its
    // request, so drop its transient screens and both of its failure messages
    // — a stale one would re-render on Forward, blaming a round that no
    // longer exists. Completed round state (grades, subset, round count) is
    // untouched and resumes when review re-enters.
    calibration_phase = "idle"
    calibration_error = null
    calibration_refine_error = null
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
    generation_loading ||
    preparing_review ||
    saving ||
    !draft_ready
  $: warn_before_unload =
    current_step !== "describe" &&
    current_step !== "done" &&
    has_unpersisted_work
  function handle_before_unload(event: BeforeUnloadEvent) {
    if (!warn_before_unload || leave_guard_suppressed) return
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
  $: current_draft = draft_ready
    ? {
        description,
        spec_type,
        name,
        property_values,
        refined_property_values,
        suggested_edits,
        batch_plan,
        batch_plan_edited,
        cached_su_cases,
        cached_minted_inputs,
        grounding_sample,
        multi_turn_batch_tag,
        single_turn_batch_tag,
        undeleted_batch_tags,
        su_driver,
        input_generator,
        judge_model,
      }
    : null
  $: if (current_draft && draft_store) {
    draft_store.set(current_draft)
  }

  // The header Reset button (SDG's is_setup pattern): appears once the
  // draft carries anything and stays through every step — the confirm's
  // wording, not the button's visibility, is what escalates with the
  // stakes. Absent under the mock (draft_ready never flips there).
  $: reset_available =
    current_draft !== null && draft_has_content(current_draft)

  // Start the wizard over: wipe the draft but CARRY the batch tags (they
  // name chains on disk that only delete-on-next-drive cleans up), then
  // reload into a fresh mount — SDG's clear-and-reload move.
  async function reset_draft_with_confirm() {
    const msg =
      trace_claims.length > 0
        ? driven_data_confirm(
            "Resetting",
            trace_claims.length,
            drive_stop === null,
          )
        : "Are you sure you want to start over? Your draft (description, eval details, and scenarios) will be discarded. This cannot be undone."
    if (!confirm(msg)) return
    const carried = draft_store ? get(draft_store) : EMPTY_BUILDER_DRAFT
    draft_ready = false
    draft_store?.set(reset_draft_keeping_tags(carried))
    try {
      await persist_draft()
    } catch (e) {
      console.error("Failed to persist the reset draft:", e)
    }
    // The reset is persisted — suppress both guards for the reload.
    leave_guard_suppressed = true
    window.location.reload()
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
      // Filter to the rendered fields: a draft written when the refine form
      // still had example fields can carry values with no surface today, and
      // restoring them would silently reach the saved spec.
      refined_property_values = keep_rendered_fields(
        saved.refined_property_values,
        RENDERED_REFINE_FIELDS,
      )
      suggested_edits = keep_rendered_fields(
        saved.suggested_edits,
        RENDERED_REFINE_FIELDS,
      )
      batch_plan = saved.batch_plan
      batch_plan_edited = saved.batch_plan_edited
      cached_su_cases = saved.cached_su_cases ?? null
      cached_minted_inputs = saved.cached_minted_inputs ?? null
      grounding_sample = saved.grounding_sample ?? null
      multi_turn_batch_tag = saved.multi_turn_batch_tag
      single_turn_batch_tag = saved.single_turn_batch_tag ?? null
      undeleted_batch_tags = saved.undeleted_batch_tags
      // Model lanes: pre-Drive-Settings drafts have no such keys.
      su_driver = saved.su_driver ?? null
      input_generator = saved.input_generator ?? null
      judge_model = saved.judge_model ?? null
      // Rebuild the shallow-routing chain up to the restored step (the
      // mount already seeded "describe") so the browser's Back walks the
      // wizard steps exactly as in the original session instead of
      // immediately leaving the builder.
      // Computed from the FILTERED refine records: a legacy draft whose
      // refine content was example fields only must not restore into an
      // empty refine form.
      const step = restore_step({
        ...saved,
        refined_property_values,
        suggested_edits,
      })
      if (step === "refine" || step === "generate") {
        goto_step("refine")
      }
      if (step === "generate") {
        goto_step("generate")
      }
    }
    draft_ready = true
  }

  // Retire the draft once the save persisted (the leave-guard hook point):
  // stop the mirror FIRST so the wizard's still-populated state can't
  // rewrite the draft after the wipe, then flush — the store's subscriber
  // writes async, and navigating before the write lands would resurrect
  // the draft on the next visit. `residual` defaults to a full wipe;
  // multi-turn passes a draft carrying only leftover cleanup tags so
  // stranded chains from earlier aborted drives still get deleted later.
  async function clear_builder_draft(
    residual: BuilderDraft = EMPTY_BUILDER_DRAFT,
  ) {
    draft_ready = false
    draft_store?.set(residual)
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

  // On a HARD page load, onMount fires during hydration — BEFORE SvelteKit's
  // router is initialized — and replaceState/pushState then throw, killing
  // onMount and wedging the loading screen. afterNavigate fires exactly once
  // the router is ready (initial load and SPA entry alike), so every history
  // call below awaits this instead of racing it.
  let router_ready: () => void
  const router_ready_promise = new Promise<void>((resolve) => {
    router_ready = resolve
  })
  afterNavigate(() => router_ready())

  onMount(async () => {
    await router_ready_promise
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

  // Resolve a candidate eval name against the task's existing specs — the
  // save guard's derived-tag comparison (case/spacing-insensitive), run
  // where a collision costs nothing. On a collision the server returns the
  // nearest available suffixed variant. Returns null when the check itself
  // fails (offline etc.) — the save-time 409 remains the backstop then.
  async function resolve_available_name(
    candidate: string,
  ): Promise<{ name: string; was_taken: boolean } | null> {
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/available_spec_name",
        {
          params: {
            path: { project_id, task_id },
            query: { name: candidate },
          },
        },
      )
      if (error || !data) return null
      return data
    } catch {
      return null
    }
  }

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
          "Couldn't classify your description. Continuing with the default 'issue' type."
        goto_step("clarify")
        return
      }
      spec_type = data.spec_type as SpecType
      // Prefill the Eval Name only while the field is untouched — the steps
      // stay mounted under browser Back, so a second Continue must not clobber
      // a name the user typed on step 3. The suggester is deterministic over
      // similar descriptions, so a second eval on this task would regenerate a
      // taken name — take the nearest available variant instead (best-effort).
      if (should_prefill_suggested_name(name)) {
        name =
          (await resolve_available_name(data.suggested_name))?.name ??
          data.suggested_name
      }
      // The classifier returns the property_values dict already keyed for
      // this spec_type. Cast to the looser Record shape consumed by
      // Questions and the refine form.
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
  // Identity snapshot of the description the current question_set was
  // generated from; null until a set successfully lands. Drives the
  // regeneration gate below.
  let question_set_source: string | null = null
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
    // A validation message about the set being replaced must not outlive it:
    // the answers it complained about are cleared with the questions below.
    questions_form_error = null
    // Pin the description this set is being generated from before the await,
    // so a later edit can't be mistaken for the text the copilot actually saw.
    const source = description
    try {
      const { data, error } = await client.POST("/api/copilot/question_spec", {
        body: {
          project_id,
          task_id,
          target_task_info: {
            task_prompt: task?.instruction ?? "",
            task_input_schema: "",
            task_output_schema: "",
          },
          target_specification: source,
        },
        signal: new_copilot_abort_signal(),
      })
      if (error || !data) {
        questions_error = "Failed to load clarifying questions."
        return
      }
      question_set = data as QuestionSet
      question_set_source = source
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

  // ── Step 3 state — refine
  // The fields the refine form renders, and therefore the only writable
  // surface declared to the refine call. Edits for any other field are
  // discarded before they can reach the saved spec (the user never saw
  // them) and reported for telemetry.
  // The builder is issue-type-only end to end (save also hardcodes the
  // issue spec_type); this list must move with spec_type if that changes.
  const RENDERED_REFINE_FIELDS: readonly string[] = ["issue_description"]
  let refined_property_values: Record<string, string | null> = {}
  // Snapshot of refined_property_values as the CODE last wrote it (refine
  // success or a seed). The form's bind:value mutates the values without
  // touching this, so "still byte-equal" means untouched model output — the
  // only content a failed refine may discard. Null (draft-restored values)
  // reads as user-owned.
  let refined_values_programmatic_json: string | null = null
  // Snapshot of the classified values that same write was derived from. A
  // failure only discards programmatic content once this no longer matches the
  // current property_values — otherwise the refined text still fits the
  // description on screen and is worth keeping.
  let refined_values_derived_from_json: string | null = null
  let suggested_edits: Record<string, SuggestedEdit> = {}
  let refine_form_error: KilnError | null = null
  let refined_preview_loading = false
  // Non-blocking: refinement failing still lands the user on an editable
  // refine step, but they should know their answers weren't incorporated.
  let refine_warning: string | null = null

  // The classified values as the refine form sees them. Every snapshot and
  // compare of the form's source goes through here, so both sides of a byte
  // compare are built the same way and key order can never differ.
  function rendered_source_json(): string {
    return JSON.stringify(
      keep_rendered_fields(property_values, RENDERED_REFINE_FIELDS),
    )
  }

  // A failed refine still lands on an editable form: seed it from the
  // current values, unless a prior visit already populated it (a re-entered
  // clarify pass must not wipe the user's Step 3 edits). Called only from
  // the failure paths; success overwrites the form from the response.
  function seed_refine_form_if_empty() {
    if (Object.keys(refined_property_values).length === 0) {
      // Rendered fields only, so a live session and a restored draft save
      // the same Spec (the restore path filters the same way).
      refined_property_values = keep_rendered_fields(
        property_values,
        RENDERED_REFINE_FIELDS,
      )
      refined_values_programmatic_json = JSON.stringify(refined_property_values)
      refined_values_derived_from_json = rendered_source_json()
    }
  }

  // A failed refine must not leave a previous round's refined text in place
  // once the description behind it changed: it would silently outrank the
  // user's newer description everywhere the spec text is read, while the
  // warning above the form says their answers were not incorporated. Discard it
  // — and the suggestions that annotate it — only when it is still exactly what
  // the code wrote AND its source has moved, so both step 3 edits and a good
  // refinement that merely hit a transient failure survive.
  function reseed_refine_form_after_failure() {
    if (
      should_invalidate_refined_values(
        refined_property_values,
        refined_values_programmatic_json,
        refined_values_derived_from_json,
        rendered_source_json(),
      )
    ) {
      refined_property_values = {}
      suggested_edits = {}
    }
    seed_refine_form_if_empty()
  }

  // Called by Questions component on Next. Fires the refinement call and
  // populates the refine form's state. Matches v1's flow:
  //   answer Qs → refining spinner → refine screen with editable suggestions.
  async function on_continue_from_clarify(
    questions_and_answers: QuestionWithAnswer[],
  ) {
    // FormContainer flips submitting=true on submit and leaves the reset to
    // us — clear it before advancing so browser Back to the clarify step
    // doesn't find a permanently spinning Next button.
    questions_submitting = false
    goto_step("refine")
    refined_preview_loading = true
    refine_warning = null
    try {
      // Declare only the rendered fields as the refinable surface, so the
      // copilot is not invited to draft content the form cannot show.
      const spec_fields: Record<string, string> = {}
      const spec_field_current_values: Record<string, string> = {}
      for (const field of field_configs) {
        if (!RENDERED_REFINE_FIELDS.includes(field.key)) continue
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
        ).getMessage()}). Edit it directly below.`
        reseed_refine_form_after_failure()
        return
      }

      const refine_response = data as {
        new_proposed_spec_edits?: ProposedSpecEdit[]
        suggested_name?: string
      }

      // Prefill the Eval Name from the model's suggestion, but only when the
      // user hasn't typed one and the suggestion passes the same filename-safe
      // validator the name field enforces. User input always wins; an invalid
      // or absent suggestion leaves the field untouched.
      if (
        should_prefill_suggested_name(name) &&
        refine_response.suggested_name &&
        filename_string_short_validator(refine_response.suggested_name) === null
      ) {
        // Same deterministic-suggester hazard as the classify prefill: take
        // the nearest available variant of the suggestion (best-effort).
        name =
          (await resolve_available_name(refine_response.suggested_name))
            ?.name ?? refine_response.suggested_name
      }

      // Start from current values, then apply the edits the form can show.
      // An edit for a field the form does not render is discarded, so
      // nothing is saved without being seen. The user gets no notice (there
      // is nothing they could do with one); telemetry carries the signal,
      // because a stray edit means the refine contract drifted.
      const split = split_refine_edits(
        refine_response.new_proposed_spec_edits ?? [],
        RENDERED_REFINE_FIELDS,
      )
      if (split.dropped_fields.length > 0) {
        // Field names are model-authored: dedupe and bound them before they
        // ride to telemetry.
        posthog.capture("eval_v2_refine_stray_edits_dropped", {
          fields: [...new Set(split.dropped_fields)]
            .slice(0, 10)
            .map((f) => f.slice(0, 64)),
        })
      }
      refined_property_values = {
        ...keep_rendered_fields(property_values, RENDERED_REFINE_FIELDS),
        ...split.refined_edits,
      }
      refined_values_programmatic_json = JSON.stringify(refined_property_values)
      // The classified values this refine ran against (property_values is not
      // touched during the call), so a later failure can tell whether the
      // description behind these values has since moved.
      refined_values_derived_from_json = rendered_source_json()
      suggested_edits = split.suggested_edits
    } catch (e) {
      if (is_abort_error(e)) return
      // Refinement is optional — the user lands on an editable refine step
      // either way — but the failure must not be silent.
      refine_warning =
        "Couldn't refine your eval from your answers. Edit it directly below."
      reseed_refine_form_after_failure()
    } finally {
      refined_preview_loading = false
    }
  }

  // The refine form's Next action: advance to Step 4 generation with
  // whatever refined_property_values the user finalized.
  // Reentry guard for the async submit below: a second activation during
  // the availability round trip (double-click, Cmd-Enter key-repeat) must
  // not advance twice — that would double-push history and start two
  // concurrent plan calls.
  let refine_submit_in_flight = false

  async function on_refine_submit() {
    if (refine_submit_in_flight) return
    refine_submit_in_flight = true
    try {
      // Early collision check on the final (possibly user-typed) name — the
      // same derived-tag rule the save guard enforces, surfaced here where
      // a rename costs nothing instead of after generation and review.
      // Best-effort: if the check itself can't run, advance — the save-time
      // 409 remains the backstop.
      refine_form_error = null
      const resolved = await resolve_available_name(name)
      if (resolved?.was_taken) {
        refine_form_error = new KilnError(
          `An eval named '${name}' already exists for this task ` +
            `('${resolved.name}' is available).`,
          null,
        )
        return
      }
      on_advance_to_generate()
    } finally {
      refine_submit_in_flight = false
    }
  }

  // ── Step 4 state — generation
  let generation_loading = false
  let generation_error: string | null = null
  // The judge the review step actually ran — save persists THIS object, so
  // the judge the user calibrated against is the judge that ships. Both
  // arms author it per-drive (author_judge; the server picks the rubric
  // framing from the task's turn mode).
  let review_judge: JudgeConfig | null = null
  // Identity snapshot of what the review judged: the SPEC TEXT only. The
  // judge prompt is authored from it and every graded claim argues it, so
  // editing it after review invalidates the review — the staleness gate
  // below then blocks (never destroys) until the user reverts or explicitly
  // re-creates. The NAME is deliberately absent: it is a save-time identity
  // (score column, dataset tags) that nothing pre-save depends on — the
  // transient judge scores under a constant draft key — so renames are
  // always free.
  let reviewed_identity: string | null = null

  // Number of cases in one batch (conversations to drive, or single-turn
  // inputs to run) — matches NUM_CASES_MAX in
  // libs/core/kiln_ai/synthetic_user/runner.py and the single-turn
  // pipeline's inputs cap.
  const NUM_CASES = 40
  // Batch plan for Step 4 — one prompt per unit of work (a conversation
  // scenario or a single-turn test input), drafted by the copilot batch
  // planner and approved (with edits/deletions) by the user before anything
  // is driven.
  type BatchPlan = { prompts: string[]; summary: string }
  let batch_plan: BatchPlan | null = null
  // The summary isn't regenerated when the user edits/deletes prompts — flag
  // that it may no longer match (mirrors the /generate route's plan UI).
  let batch_plan_edited = false
  // Snapshot of the prompts a drive actually ran — gates the Next-to-review
  // action so results are never presented for a plan edited after the drive.
  let driven_prompts_json: string | null = null
  // The plan's generated synthetic users, reused on a re-drive while the
  // plan and spec are byte-unchanged: SU cases don't depend on the run
  // config, so a fix-config-then-drive-again loop shouldn't re-pay the
  // multi-minute generation. Rides the persisted draft.
  let cached_su_cases: CachedSuCases | null = null
  // The single-turn arm's minted inputs, reused on a re-run while the plan
  // and input-generator model are byte-unchanged. Rides the persisted draft.
  let cached_minted_inputs: CachedMintedInputs | null = null
  // The auto-picked task sample grounding the single-turn plan and input
  // generation (dataset grounding, the V1 restore): picked once per plan
  // (highly-rated run preferred, else most recent), folded into both calls'
  // data-guide param, and persisted on the saved Spec for provenance. Rides
  // the draft so a restored session mints with the same grounding its plan
  // was drafted under. Null when the task has no runs — grounding is
  // best-effort, never a gate.
  let grounding_sample: TaskSampleExample | null = null
  // Approved plan length drives the batch size; NUM_CASES is the requested
  // plan size before any deletions.
  $: planned_total = batch_plan?.prompts.length ?? NUM_CASES
  // Which loading stage Step 4 is in — drives the progress screen only.
  // The interactive plan-approval view is DERIVED (show_plan_approval below),
  // not a phase, so no code path can strand it behind a stale flag.
  // generating_cases is the multi-turn SU generation; minting_inputs is the
  // single-turn input generation — the same slot in each arm's sequence.
  type GenerationPhase =
    | "idle"
    | "authoring_judge"
    | "preflight"
    | "planning"
    | "generating_cases"
    | "minting_inputs"
    | "running_pipeline"
  let generation_phase: GenerationPhase = "idle"
  $: pipeline_running =
    generation_loading && generation_phase === "running_pipeline"
  $: show_plan_approval =
    batch_plan !== null &&
    !generation_loading &&
    !generation_error &&
    // The preparing-review gate owns the screen between drive and review.
    !preparing_review &&
    claims_gate_error === null
  // Eager lane resolution when the plan surface becomes visible, so the
  // primary run starts instantly and the models link opens a prefilled
  // dialog. Fire-and-forget: prepopulate_lanes only fills null lanes (never
  // overwrites a draft/user choice) and its own guard makes the drive's
  // later call a no-op, so this never starts a drive nor races the run flow.
  $: if (show_plan_approval && !lanes_prepopulated) {
    void prepopulate_lanes()
  }
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
    minting_done = 0
    minting_total = 0
  }

  // Input-minting progress (single-turn): the generate-inputs batch job's
  // completed/total, polled while the minting phase runs.
  let minting_done = 0
  let minting_total = 0

  // The cases whose conversations were actually driven (chains exist on
  // disk). Save mints one EvalInput per driven case — the eval slice the
  // runner re-drives per run config.
  let driven_cases: SyntheticUserCaseWire[] = []
  // The current batch's item list (cases on multi-turn, minted inputs on
  // single-turn) and its per-slot results, kept across drives so a retry
  // can TOP OFF the missing slots — drive only them, into the same batch
  // tag — instead of replacing the batch and re-billing its paid
  // successes. Not drafted: results don't survive a reload, so neither
  // does the batch's slot state.
  let batch_cases: SyntheticUserCaseWire[] | null = null
  let batch_inputs: string[] | null = null
  let built_by_case: (TraceClaims | null)[] = []
  // Slots whose conversation was successfully driven. Guards driven_cases
  // against a duplicate append when a top-off re-drives a case that drove
  // but failed a later stage — its case must reach save exactly once.
  let driven_slots = new Set<number>()
  // The synthetic-user model driven_cases actually ran with, captured at
  // batch commit. Save stamps THIS onto the minted items — the live
  // su_driver picker can change after the drive (Advanced dialog), and the
  // stamp must describe the conversations that exist, not a later pick.
  let driven_su_driver: ModelChoice | null = null
  // batch_tag from each arm's pipeline batch_started event — passed to the
  // save endpoint so the backend can tag the matching runs for the eval
  // dataset.
  let multi_turn_batch_tag: string | null = null
  let single_turn_batch_tag: string | null = null
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
  // continue with the survivors via Next (iff any) or Drive again. No
  // failure is shown without an action, and no failure silently shrinks the
  // batch; all-failed is the same screen with Next naturally absent.
  let drive_stop: DriveStop | null = null
  // Per-case failure messages from the last drive's case_failed frames —
  // aggregated into the stop banner's "most common" diagnosis.
  let case_failure_messages: string[] = []
  // The run config the drive ran with — named in the stop banner so a
  // config-class failure is diagnosable without leaving the wizard. The
  // model rides along for the abort banner (the model IS the usual culprit).
  let drive_run_config_name: string | null = null
  let drive_run_config_model: string | null = null
  // Set when the drive had to fall back to the first available run config
  // because the task has no default set — surfaced in the UI so testers
  // know which model the eval data was generated against.
  let fallback_run_config_name: string | null = null

  // Resolve the target run config a drive runs on (both arms): prefer the
  // task's default; if none set, fall back to the first available config so
  // the user doesn't have to detour into task settings just to try v2.
  // Returns null AFTER setting generation_error (task unrunnable or the
  // config isn't a Kiln agent one). Re-fetches the task first: the default
  // can change while the wizard is open — the stop banner's own recovery
  // loop sends the user to /run in another tab to fix it — and driving with
  // the mount-time snapshot would resolve the OLD default.
  async function resolve_drive_run_config(): Promise<{
    id: string
    model_name: string
    model_provider: string
  } | null> {
    task = await load_task(project_id, task_id)
    if (!task?.id) {
      generation_error = "Task not loaded."
      return null
    }
    await load_task_run_configs(project_id, task.id)
    const run_configs =
      get(run_configs_by_task_composite_id)[
        get_task_composite_id(project_id, task.id)
      ] ?? []
    if (run_configs.length === 0) {
      generation_error =
        "Task has no run configs. Create one before creating eval data."
      return null
    }
    const default_match = run_configs.find(
      (c) => c.id === task!.default_run_config_id,
    )
    const chosen_config = default_match ?? run_configs[0]
    fallback_run_config_name = default_match ? null : chosen_config.name
    drive_run_config_name = chosen_config.name
    const rcp = chosen_config.run_config_properties
    if (!isKilnAgentRunConfig(rcp)) {
      generation_error =
        "Creating eval data requires a Kiln Agent run config; the selected one isn't."
      return null
    }
    drive_run_config_model = rcp.model_name
    if (!chosen_config.id) {
      generation_error = "The selected run config has no id."
      return null
    }
    return {
      id: chosen_config.id,
      model_name: rcp.model_name,
      model_provider: rcp.model_provider_name,
    }
  }

  // ── Step 4 — both arms are plan-first over one pipeline shape.
  //
  // Sequence (shared):
  //   1. POST copilot/batch_plan → one prompt per unit of work; the user
  //      approves (edit/delete/regenerate) before anything runs.
  //   2. Pull the task's default run config and send its ID — the server
  //      drives the task with the saved config verbatim (model, prompt,
  //      sampling, tools). Both arms require a KilnAgentRunConfig.
  //   3. Author the judge (author_judge — the server frames the rubric from
  //      the task's turn mode), then preflight every model lane with
  //      one-word completions — a dead key/model stops the drive before any
  //      spend.
  //   4. Multi-turn: POST /multiturn_sdg/generate_cases with the approved
  //      prompts → ONE batch call, one synthetic-user case per prompt.
  //      Single-turn: start_generate_inputs_batch → one test input minted
  //      locally per prompt on the input-generator lane.
  //   5. One SSE stream runs the pipeline per case — multi_turn_pipeline
  //      ([drive → judge]) or single_turn_pipeline ([run → judge]) — and
  //      the PipelineEvent frames drive progress + the review results.
  //
  const TURNS_PER_CASE = 5

  // ── Model lanes (SDG's Generation Settings pattern). The primary button
  // runs immediately with these lanes resolved to their defaults; the
  // "Advanced" dialog lets the user pick them first — the user simulator
  // (multi-turn), the input generator (single-turn), and the judge — and
  // its submit starts the run the same way. The committed lanes ride the
  // persisted draft; the builder has no hardcoded model or provider
  // anywhere.
  let su_driver: ModelChoice | null = null
  let input_generator: ModelChoice | null = null
  let judge_model: ModelChoice | null = null
  let drive_settings_dialog: Dialog | null = null
  // Dropdown bindings: the combined "provider_id/model_id" string plus the
  // parsed ids the dropdown maintains. Committed to the lanes on submit —
  // closing the dialog without submitting discards dropdown changes.
  let su_model_combined: string | null = null
  let su_model_id: string | null = null
  let su_provider_id: string | null = null
  let input_gen_model_combined: string | null = null
  let input_gen_model_id: string | null = null
  let input_gen_provider_id: string | null = null
  let judge_model_combined: string | null = null
  let judge_model_id: string | null = null
  let judge_provider_id: string | null = null
  let drive_settings_submitting = false
  // Typed as KilnError so the dialog's FormContainer renders it in its own
  // centered error slot, like every other form in the app.
  let drive_settings_error: KilnError | null = null
  // One pre-population pass per mount; lanes the draft restored (or the
  // user committed) are never overwritten — only null lanes are filled.
  let lanes_prepopulated = false

  // Judge lane from the task's LAST SAVED eval — the replay-what-worked
  // tier of pre-population. The judge lives on the eval's current config
  // (v2 configs keep the model in typed properties, legacy at the root).
  // The synthetic-user lane has no such tier: drive settings live on eval
  // items, and each wizard run picks its own (registry suggestion by
  // default). Best-effort: any miss returns null and pre-population falls
  // through to suggestions.
  async function last_saved_eval_judge(): Promise<ModelChoice | null> {
    const { data, error } = await client.GET(
      "/api/projects/{project_id}/tasks/{task_id}/evals",
      { params: { path: { project_id, task_id } } },
    )
    if (error || !data) return null
    // The evals list rides in an envelope alongside a count of evals that
    // failed to load; only the readable ones matter for judge pre-population.
    const evals = [...data.evals].sort((a, b) =>
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    )
    const judge_eval = evals.find((e) => e.id && e.current_config_id) ?? null
    let judge: ModelChoice | null = null
    if (judge_eval?.id && judge_eval.current_config_id) {
      const configs = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}/eval_configs",
        {
          params: {
            path: { project_id, task_id, eval_id: judge_eval.id },
          },
        },
      )
      const config = configs.data?.find(
        (c) => c.id === judge_eval.current_config_id,
      )
      const props = config?.properties as
        | { model_name?: unknown; model_provider?: unknown }
        | undefined
      const model =
        typeof props?.model_name === "string"
          ? props.model_name
          : config?.model_name ?? null
      const provider =
        typeof props?.model_provider === "string"
          ? props.model_provider
          : config?.model_provider ?? null
      if (model && provider) {
        judge = model_choice(model, provider)
      }
    }
    return judge
  }

  // Fill null lanes: draft (already restored into the lane vars) → the
  // last saved eval's judge (judge lane only) → first registry-suggested
  // model among the connected providers (same flags that power the
  // Recommended badges). A lane with no usable model anywhere stays null:
  // the dropdown's empty state names the way out and submit refuses to
  // start.
  async function prepopulate_lanes() {
    if (lanes_prepopulated) return
    lanes_prepopulated = true
    const su_needed = is_multi_turn && su_driver === null
    const input_gen_needed = !is_multi_turn && input_generator === null
    if (!su_needed && !input_gen_needed && judge_model !== null) return
    if (judge_model === null) {
      try {
        const saved_judge = await last_saved_eval_judge()
        if (saved_judge) judge_model = saved_judge
      } catch (e) {
        console.warn("Could not read the last saved eval's judge model:", e)
      }
    }
    await load_available_models()
    const models = get(available_models)
    if (is_multi_turn && su_driver === null) {
      const suggested = build_suggested_models(models, "data_gen")[0]
      if (suggested) {
        su_driver = model_choice(suggested.model_id, suggested.provider_id)
      }
    }
    if (!is_multi_turn && input_generator === null) {
      // Same suggestion tier as /generate's input-generation dropdown (a
      // saved eval records no input-generator, so there is no replay tier).
      const suggested = build_suggested_models(models, "data_gen")[0]
      if (suggested) {
        input_generator = model_choice(
          suggested.model_id,
          suggested.provider_id,
        )
      }
    }
    if (judge_model === null) {
      const suggested = build_suggested_models(models, "evals")[0]
      if (suggested) {
        judge_model = model_choice(suggested.model_id, suggested.provider_id)
      }
    }
  }

  async function open_drive_settings() {
    drive_settings_error = null
    drive_settings_dialog?.show()
    await prepopulate_lanes()
    // Reseed the dropdowns from the committed lanes (also discards any
    // uncommitted picks from a previously cancelled dialog).
    su_model_combined = su_driver
      ? `${su_driver.model_provider}/${su_driver.model_name}`
      : su_model_combined
    input_gen_model_combined = input_generator
      ? `${input_generator.model_provider}/${input_generator.model_name}`
      : input_gen_model_combined
    judge_model_combined = judge_model
      ? `${judge_model.model_provider}/${judge_model.model_name}`
      : judge_model_combined
  }

  // Run-immediately (the plan-approval primary button): resolve the default
  // model lanes (draft → saved-eval judge → registry suggestion) and start
  // the drive without a settings detour — the common path is "just make my
  // data". If a lane can't be resolved (no usable model anywhere), the
  // drive opens the dialog instead of running — fail-loud recovery, never a
  // silent substitution of some other model. "Advanced" opens the same
  // dialog up front for users who want to pick the models before spending.
  async function start_drive_with_defaults() {
    await prepopulate_lanes()
    if (is_multi_turn) {
      on_drive_multi_turn()
    } else {
      void on_drive_single_turn()
    }
  }

  // The authored multi-turn judge prompt, cached against BOTH authoring
  // inputs — spec text and the task prompt (the task is re-fetched every
  // drive, so its instruction can change mid-session too): a re-drive with
  // both unchanged reuses it instead of re-paying the authoring call; any
  // edit to either misses and re-authors.
  let authored_judge_cache: {
    spec_text: string
    task_prompt: string
    prompt: string
  } | null = null

  // Author a spec-tailored judge prompt via the studio (kiln_server's
  // multi-turn judge author) — the multi-turn counterpart of clarify_spec's
  // judge_result. Authoring is REQUIRED: any failure, deadline expiry, or
  // unusable prompt throws, stopping the drive on the same retryable error
  // surface as every other copilot step (v1's contract too: no server, no
  // spec — a silently generic judge would mean a silently lenient eval).
  // A USER abort propagates as an AbortError, cancelling the drive.
  async function author_judge_prompt_for_spec(
    user_signal: AbortSignal,
  ): Promise<string> {
    const spec = spec_text()
    const task_prompt = task?.instruction ?? ""
    if (
      authored_judge_cache?.spec_text === spec &&
      authored_judge_cache.task_prompt === task_prompt
    ) {
      return authored_judge_cache.prompt
    }
    const { signal, timed_out } = with_deadline(
      user_signal,
      JUDGE_COPILOT_DEADLINE_MS,
    )
    let data, error
    try {
      ;({ data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/author_judge",
        {
          params: { path: { project_id, task_id } },
          body: {
            target_specification: spec,
            target_task_prompt: task_prompt,
          },
          signal,
        },
      ))
    } catch (e) {
      // Deadline check FIRST: its rejection is a TimeoutError (not
      // AbortError) in most engines, but engines vary — timed_out() is the
      // authoritative discriminator either way.
      if (timed_out()) {
        posthog.capture("eval_v2_judge_author_failure", { reason: "timeout" })
        throw new KilnError("Authoring your judge took too long. Try again.")
      }
      if (is_abort_error(e)) throw e
      posthog.capture("eval_v2_judge_author_failure", {
        reason: "request_failed",
      })
      // Thrown = the request never completed (network/transport) — the one
      // case where "check your connection" is the right diagnosis.
      throw new KilnError(
        "Couldn't reach the server to author a judge for your spec. Check your connection and try again.",
      )
    }
    if (error || !data?.judge_prompt) {
      posthog.capture("eval_v2_judge_author_failure", {
        reason: "request_failed",
      })
      // The request completed and the server said no — surface ITS detail
      // (e.g. "API key not configured"), like every sibling copilot call.
      throw new KilnError(
        `Couldn't author a judge for your spec: ${createKilnError(error).getMessage()}`,
      )
    }
    // Same mechanical validation as the refine path: the prompt renders
    // into the judge harness verbatim, so an unusable one is a failure.
    const validation_error = validate_refined_judge_prompt(data.judge_prompt)
    if (validation_error) {
      posthog.capture("eval_v2_judge_author_failure", {
        reason: "invalid_authored_prompt",
      })
      throw new KilnError("The authored judge prompt wasn't usable. Try again.")
    }
    authored_judge_cache = {
      spec_text: spec,
      task_prompt,
      prompt: data.judge_prompt,
    }
    return data.judge_prompt
  }

  // Commit the lanes and start the run. Refuses on an unset lane — the
  // SDG flow would fall through to raw server errors here; we stop with a
  // visible error instead.
  function submit_drive_settings() {
    drive_settings_submitting = false
    const su_ok = !is_multi_turn || (su_model_id && su_provider_id)
    const input_gen_ok =
      is_multi_turn || (input_gen_model_id && input_gen_provider_id)
    if (!su_ok || !input_gen_ok || !judge_model_id || !judge_provider_id) {
      drive_settings_error = new KilnError(
        is_multi_turn
          ? "Select a model to play the user and a judge model to continue."
          : "Select a model to write the test inputs and a judge model to continue.",
      )
      return
    }
    if (is_multi_turn && su_model_id && su_provider_id) {
      su_driver = model_choice(su_model_id, su_provider_id)
    }
    if (!is_multi_turn && input_gen_model_id && input_gen_provider_id) {
      input_generator = model_choice(input_gen_model_id, input_gen_provider_id)
    }
    judge_model = model_choice(judge_model_id, judge_provider_id)
    drive_settings_error = null
    drive_settings_dialog?.close()
    if (is_multi_turn) {
      on_drive_multi_turn()
    } else {
      void on_drive_single_turn()
    }
  }

  // Events on the merged review-pipeline stream (one stream runs
  // [drive → judge → claims] per case; see eval_builder_api.multi_turn_pipeline).
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
        // The structured conversation behind raw_output (multi-turn); the
        // trace modal renders it in the chat UI. Absent on legacy streams.
        trace?: TraceClaims["trace"]
      }
    | {
        type: "case_failed"
        case_index: number
        stage: "drive" | "run" | "judge"
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
    | {
        type: "batch_aborted"
        error: string
        stage: "drive" | "run" | "judge"
      }

  // THE spec text — the single source every consumer reads (batch planning,
  // synthetic-user generation, the default judge prompt, and the saved Spec),
  // so no two stages can see different text. Step 3's refined values win;
  // property_values covers a skipped refine; Step 1's free text is the floor.
  // Declared reactively, referencing the three state vars DIRECTLY so
  // Svelte's compile-time dependency tracking sees them — the staleness
  // gate derives from this, and a plain function call inside a `$:`
  // statement would track nothing (a hoisted function's reads are invisible
  // to the compiler), leaving the gate frozen across description edits.
  $: current_spec_text =
    ((Object.keys(refined_property_values).length > 0
      ? refined_property_values
      : property_values
    ).issue_description as string | null) ?? description

  // Callable form for the imperative sites (drive snapshots, save, plan
  // guidance). Delegates so the two can't drift; reactive statements run at
  // component init, before any of those sites can fire.
  function spec_text(): string {
    return current_spec_text
  }

  // Step 4 part 1 — plan (both arms). Ask the batch planner for one prompt
  // per case — a conversation scenario or a single-turn test input —
  // balanced ~50/50 expected-pass / expected-fail (the balance policy lives
  // in batch_plan_guidance), then pause on the approval screen. Nothing is
  // driven until the user approves.
  async function on_plan_batch() {
    generation_loading = true
    generation_error = null
    batch_plan = null
    batch_plan_edited = false
    // The cached synthetic users / minted inputs belong to the discarded
    // plan (the byte compare would reject them anyway) — drop the payload
    // from the draft.
    cached_su_cases = null
    cached_minted_inputs = null
    reset_pipeline_counters()
    drive_stop = null
    // Deliberately NOT clearing the live batch tag (save still needs it)
    // or undeleted_batch_tags: the next drive passes the cleanup list as
    // replace_batch_tags, and the server deletes those batches once the new
    // drive has produced replacements.
    // Claims belong to the discarded plan's results — clear them so
    // browser Forward can't re-enter review over stale results.
    trace_claims = []
    trace_reviews = []
    selected_trace_indices = []
    driven_prompts_json = null
    // The batch's slot bookkeeping goes with the results: a later drive
    // must start a fresh batch, never top off a discarded one.
    batch_cases = null
    batch_inputs = null
    built_by_case = []
    driven_slots = new Set()
    // Calibration rounds calibrated the discarded results' judge.
    reset_calibration_state()
    generation_phase = "planning"
    try {
      // Single-turn grounding: re-pick with each plan (the dataset can have
      // changed since the last one). Best-effort — a fetch failure just
      // plans ungrounded, like a task with no runs yet. Machine-generated
      // runs are excluded unless a human rated them 5-star: the wizard's own
      // pipeline (and the generators) persist synthetic runs into this same
      // dataset, and grounding on those would feed the planner its own
      // output — the exact drift this rider exists to prevent.
      if (!is_multi_turn) {
        try {
          grounding_sample = (
            await fetch_task_sample_candidates(
              project_id,
              task_id,
              (run) =>
                run.input_source?.type !== "synthetic" ||
                is_five_star_rated(run),
            )
          ).selected_example
        } catch (e) {
          console.warn("Could not pick a grounding sample:", e)
          grounding_sample = null
        }
      }
      const { data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/copilot/batch_plan",
        {
          params: { path: { project_id, task_id } },
          body: {
            guidance: is_multi_turn
              ? multiturn_plan_guidance(spec_text())
              : single_turn_plan_guidance(spec_text()),
            count: NUM_CASES,
            // The grounding sample rides the planner's data-guide param
            // (multi-turn plans scenarios, not inputs — no guide there).
            data_guide: is_multi_turn
              ? null
              : grounding_data_guide(grounding_sample),
          },
          signal: new_copilot_abort_signal(),
        },
      )
      if (error || !data) {
        generation_error = `Failed to draft ${plan_noun}.`
        return
      }
      // Clamp: the planner is an LLM and can over-deliver or emit blanks;
      // both would 422 at drive time with no visible cause.
      const prompts = data.prompts
        .map((p) => p.trim())
        .filter(Boolean)
        .slice(0, NUM_CASES)
      if (prompts.length === 0) {
        generation_error = `The planner returned no usable ${plan_noun}. Retry.`
        return
      }
      batch_plan = { prompts, summary: data.summary }
    } catch (e) {
      if (is_abort_error(e)) return
      generation_error = e instanceof Error ? e.message : "Planning failed."
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
  // Accepted has-data state (clean drive, or survivors accepted via Next):
  // Drive is hidden — Next (to review) is the only forward action. On the
  // stop screen Drive stays visible as the re-drive recovery.
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
    // The batch's slot bookkeeping goes with the results: a later drive
    // must start a fresh batch, never top off a discarded one.
    batch_cases = null
    batch_inputs = null
    built_by_case = []
    driven_slots = new Set()
    reset_pipeline_counters()
    // The loop's rounds belong to the discarded results.
    reset_calibration_state()
  }

  function on_delete_plan_prompt(index: number) {
    if (!batch_plan) return
    // Deleting a row from a plan with driven results discards those results
    // (the plan no longer matches what ran) — confirm at the destructive
    // click. A pristine or merely-edited plan deletes rows freely, matching
    // SDG's unconfirmed row deletes.
    if (has_driven_results) {
      const msg = driven_data_confirm(
        `Editing the ${plan_noun}`,
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
      plan_noun,
    })
    if (!confirm(msg)) return
    on_plan_batch()
  }

  // Step 4 (multi-turn) part 2 — drive from the approved plan. The approved
  // prompts become synthetic-user cases in ONE batch call (case i ← prompt i
  // via generate_cases' case_prompts), then a single multi_turn_pipeline stream
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
        const provider = provider_name_from_id(l.model_provider)
        const { error } = await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/eval_builder/preflight_model",
          {
            params: { path: { project_id, task_id } },
            body: {
              model_name: l.model_name,
              // l.model_provider is a plain string here; PreflightModelApiInput
              // types model_provider as ModelProviderName, so we cast — the
              // route 422s on a value outside the enum.
              model_provider: l.model_provider as ModelProviderName,
            },
            signal,
          },
        )
        if (error) {
          // The route's typed error nests {code, message} inside the
          // handler's {message} wrapper — unwrap it directly: the message
          // IS the diagnosis, and createKilnError would prefix "Unexpected
          // error:" onto it. Fall back for any other shape.
          const wrapped = (error as { message?: string | { message?: string } })
            .message
          const detail =
            typeof wrapped === "string" ? wrapped : wrapped?.message
          return {
            lane: l.lane,
            ok: false,
            message: detail || createKilnError(error).getMessage(),
            model,
            provider,
          }
        }
        return { lane: l.lane, ok: true }
      }),
    )
    return first_preflight_failure(outcomes)
  }

  async function on_drive_multi_turn() {
    // The plan surface's primary button calls this directly (no FormContainer
    // submit debounce anymore), so guard reentry: a double-click during lane
    // resolution must not start a second concurrent pipeline.
    if (generation_loading) return
    if (!batch_plan || batch_plan.prompts.length === 0) {
      generation_error = "No approved scenarios. Draft scenarios first."
      return
    }
    // Lanes uncommitted (internal re-drive path reached before any
    // Drive Settings submit) — ask, don't guess.
    const chosen_su = su_driver
    const chosen_judge_model = judge_model
    if (!chosen_su || !chosen_judge_model) {
      open_drive_settings()
      return
    }
    const approved_prompts = batch_plan.prompts
    generation_loading = true
    generation_error = null
    // Clear a previous drive's stop banner up front: authoring can fail
    // before the post-preflight clear, and its error must not render
    // alongside a stale stop screen.
    drive_stop = null
    generation_phase = "preflight"
    // Set once the drive's batch bookkeeping is committed; the abort
    // handler must leave the previous results untouched before that point.
    let drive_committed = false

    try {
      // 1. Resolve target_run_config (task default → first config). The
      // server drives the task with the saved config verbatim by id, so
      // model, prompt, sampling, and TOOLS all match a manual run.
      const drive_config = await resolve_drive_run_config()
      if (!drive_config) return
      const target_run_config_id = drive_config.id

      // 2. The judge, resolved BEFORE the pipeline (not just before the
      // stream) so the preflight below covers the judge lane too — the
      // judge-dies-after-drives case is the expensive one. Runs on the
      // user's picked judge model. Authoring is REQUIRED — a failure throws
      // to the drive's error surface (retryable, nothing spent yet:
      // authoring deliberately precedes preflight and SU spend) — and the
      // per-spec cache makes re-drives free. A user abort (Back/navigation)
      // during it cancels the whole drive.
      generation_phase = "authoring_judge"
      const authored = await author_judge_prompt_for_spec(
        new_copilot_abort_signal(),
      )
      const judge: JudgeConfig = {
        prompt: authored,
        model_name: chosen_judge_model.model_name,
        model_provider: chosen_judge_model.model_provider,
      }
      generation_phase = "preflight"

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
            model_name: drive_config.model_name,
            model_provider: drive_config.model_provider,
          },
          {
            lane: "synthetic-user driver",
            model_name: chosen_su.model_name,
            model_provider: chosen_su.model_provider,
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

      // 4. Preflight passed. Resolve the synthetic-user cases BEFORE
      // committing to a drive shape: the drive plan below compares them to
      // the current batch to pick top-off vs fresh, and a generation
      // failure here leaves the previous drive's results intact. Their
      // generation depends only on the plan and the spec — never the run
      // config — so a re-drive with both byte-unchanged (the
      // fix-config-then-drive-again recovery loop) reuses the cached cases
      // instead of re-paying the multi-minute copilot call. Any plan edit
      // or New Batch Plan misses the cache.
      //
      // A batch whose every slot is filled but which is short of the plan
      // lost cases to upstream salvage. Retrying with the cached list would
      // replace the batch with the same shortfall forever; only a fresh
      // generation can supply the missing scenarios.
      if (
        batch_cases !== null &&
        built_by_case.length > 0 &&
        built_by_case.every((s) => s !== null) &&
        batch_cases.length < approved_prompts.length
      ) {
        cached_su_cases = null
      }
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
        generation_phase = "generating_cases"
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
          generation_error = "Failed to create eval inputs from the scenarios."
          return
        }
        cases = cases_resp.data.cases as SyntheticUserCaseWire[]
        cached_su_cases = {
          prompts_json: JSON.stringify(approved_prompts),
          spec_text: spec_text(),
          cases,
        }
      }

      // 5. The drive plan: TOP OFF the current batch — drive only the
      // missing slots, into the same batch tag, keeping the paid
      // successes — when the batch was driven from these exact cases under
      // the same judge and synthetic user; otherwise a fresh batch under
      // replace semantics.
      const lanes_unchanged = drive_lanes_unchanged({
        judge,
        batch_judge: review_judge,
        su: chosen_su,
        batch_su: driven_su_driver,
      })
      const drive_plan = plan_drive({
        items: cases,
        batch_items: lanes_unchanged ? batch_cases : null,
        built_slots: built_by_case,
        batch_tag: multi_turn_batch_tag,
        undeleted_batch_tags,
      })
      if (drive_plan.top_off) {
        posthog.capture("eval_v2_drive_top_off", {
          num_missing: drive_plan.items.length,
        })
      }

      // 6. Commit. On a fresh drive every undeleted previous batch is
      // superseded from here (the pipeline deletes their chains once this
      // drive has produced replacements) and the slate resets; a top-off
      // keeps the batch's results and bookkeeping — it only fills holes.
      // The synthetic-user stamp flips with the cases (and rolls back with
      // them below if nothing is driven).
      const previous_batch_tag = multi_turn_batch_tag
      const previous_driven_cases = driven_cases
      const previous_driven_su_driver = driven_su_driver
      const previous_batch_cases = batch_cases
      const previous_built_by_case = built_by_case
      const previous_driven_slots = driven_slots
      // The judge/identity stamps roll back with the results: a
      // nothing-driven drive restores the previous batch, and the stamps
      // must keep describing the verdicts on screen, not the failed
      // attempt's lanes.
      const previous_review_judge = review_judge
      const previous_reviewed_identity = reviewed_identity
      driven_su_driver = chosen_su
      if (!drive_plan.top_off) {
        trace_claims = []
        trace_reviews = []
        selected_trace_indices = []
        driven_cases = []
        driven_slots = new Set()
        batch_cases = cases
        // Salvage can drop cases upstream: the batch's slot count is what
        // actually came back, not the plan size.
        built_by_case = new Array(cases.length).fill(null)
        driven_prompts_json = JSON.stringify(approved_prompts)
      }
      pipeline_total_cases = drive_plan.items.length
      reset_pipeline_counters()
      // A fresh drive means fresh conversations — and a top-off adds
      // some — so the calibration loop starts over either way.
      reset_calibration_state()
      drive_committed = true

      // 7. Remember the judge (the ONE JudgeConfig shape used by review and
      // save alike, resolved at step 2) and identity BEFORE the pipeline
      // runs so save can verify nothing changed under the results.
      review_judge = judge
      reviewed_identity = spec_text()

      // 8. One SSE stream runs the whole pipeline: [drive → judge → claims]
      // per case. POST endpoint, so fetch + shared SSE reader (EventSource
      // is GET-only).
      generation_phase = "running_pipeline"
      const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval_builder/multi_turn_pipeline`
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          cases: drive_plan.items,
          turns: TURNS_PER_CASE,
          target_run_config_id,
          su_driver: chosen_su,
          // A top-off drives into the existing batch's tag; null lets the
          // server mint a fresh one.
          batch_tag: drive_plan.batch_tag,
          replace_batch_tags: drive_plan.replace_batch_tags,
          judge,
        }),
        signal: new_copilot_abort_signal(),
      })

      if (!response.ok || !response.body) {
        // The banner speaks plain language; the route and status code are
        // debugging detail, so they go to the console only.
        const detail = await error_detail(response)
        console.error(
          `multi_turn_pipeline failed (${response.status}): ${detail}`,
        )
        generation_error = eval_data_error(detail)
        return
      }

      // Results fill the batch's slots as case_judged events arrive (cases
      // complete out of order); a top-off's stream indices map back to
      // their batch slots, so its results land beside the kept ones.
      let any_case_driven = false
      // Set by a batch_aborted frame: a config-scoped judge failure aborted
      // the batch server-side. Cases judged before it remain valid.
      let batch_abort: { error: string; stage: string } | null = null
      // Set by the batch_completed frame — the server's ONLY signal that the
      // drive loop finished cleanly and _delete_superseded_batches actually
      // ran. A batch_failed/abort tears the drive down before that delete, so
      // without this flag the superseded tags would be dropped as deleted
      // when they are still on disk.
      let batch_completed = false
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
          // The slot guard keeps a case in the slice exactly once: a
          // top-off can re-drive a case whose earlier attempt drove but
          // never judged.
          const slot = drive_plan.slot_of_stream_index[event.case_index]
          if (slot !== undefined && !driven_slots.has(slot)) {
            driven_slots.add(slot)
            driven_cases = [...driven_cases, drive_plan.items[event.case_index]]
          }
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
          // The per-batch tag + slot make the trace id unique across
          // batches, so a stale claims build from a prior batch can't pass
          // patch_trace_claims' identity guard and corrupt the trace at
          // the same index; within a batch a top-off reuses its slot's id.
          const slot = drive_plan.slot_of_stream_index[event.case_index]
          if (slot === undefined) {
            console.error(
              `multi_turn_pipeline: case_judged for unknown case_index ${event.case_index}`,
            )
          } else {
            built_by_case[slot] = {
              trace_id: `${multi_turn_batch_tag}_case_${slot}`,
              leaf_run_id: event.leaf_run_id || null,
              raw_input: event.raw_input,
              raw_output: event.raw_output,
              judge_score: event.judge_score,
              judge_reasoning: event.judge_reasoning,
              claims: null,
              final_judgement: null,
              claims_state: "unbuilt",
              claims_error: null,
              // The structured trace powers the modal's chat rendering;
              // null when the stream didn't carry it (legacy /
              // single-turn).
              trace: event.trace ?? null,
            }
            judged_case_count += 1
          }
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
          // Same sentence as the request-level failure above: the pipeline
          // name is debugging detail, so it goes to the console only.
          console.error(`multi_turn_pipeline failed: ${event.message}`)
          generation_error = eval_data_error(event.message)
          break stream_loop
        } else if (event.type === "batch_aborted") {
          posthog.capture("eval_v2_pipeline_batch_aborted", {
            stage: event.stage,
          })
          // Keep draining: results that raced past the abort frame are
          // still valid survivors; the server ends the stream right after.
          batch_abort = { error: event.error, stage: event.stage }
        } else if (event.type === "batch_completed") {
          // The drive loop finished cleanly server-side; its totals are
          // already reflected in the rows. This frame is the delete signal.
          batch_completed = true
        }
        // The `complete` terminator ends the loop.
      }
      if (any_case_driven) {
        if (batch_completed) {
          // batch_completed is the server's guarantee that the drive loop
          // ran to completion and deleted the superseded batches — only now
          // are their chains gone, so drop them from the cleanup list. A
          // failed or aborted drive never reaches that delete, so its tags
          // ride to the next drive's replace_batch_tags (idempotent, so
          // re-passing an already-deleted tag is harmless).
          undeleted_batch_tags = undeleted_batch_tags.filter(
            (t) => !drive_plan.replace_batch_tags.includes(t),
          )
        }
      } else {
        // Nothing was driven: no replacement chains, no deletions — keep
        // pointing at the previous batch (its cases, slots, and the
        // synthetic user that drove them) so save/cleanup/top-off still
        // work.
        multi_turn_batch_tag = previous_batch_tag
        driven_cases = previous_driven_cases
        driven_su_driver = previous_driven_su_driver
        batch_cases = previous_batch_cases
        built_by_case = previous_built_by_case
        driven_slots = previous_driven_slots
        // The stamps roll back with the results: they must keep describing
        // the verdicts on screen, not the failed attempt's lanes.
        review_judge = previous_review_judge
        reviewed_identity = previous_reviewed_identity
      }

      // Compact survivors BEFORE any error/warning path: completed verdicts
      // are paid results and must never be discarded by a late failure.
      // Live review entries win over the slots' drive-time copies, so a
      // kept case's built claims survive the compaction.
      const complete = compact_batch_slots(built_by_case, trace_claims)
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
      if (is_abort_error(e)) {
        // A user abort mid-stream leaves whatever cases completed as paid
        // results on disk. Once the drive was committed, compact them so
        // they stay visible, and restore the stop banner when the batch is
        // short — without it the retry (top-off) affordance is unreachable
        // from the accepted-data screen. Pre-commit aborts touched nothing.
        if (drive_committed) {
          const complete = compact_batch_slots(built_by_case, trace_claims)
          if (complete.length > 0) {
            trace_claims = complete
            trace_reviews = build_trace_reviews(complete)
            selected_trace_indices = select_review_subset(complete)
            const failed = approved_prompts.length - complete.length
            if (failed > 0) {
              drive_stop = {
                survivors: complete.length,
                failed,
                dominant_error: dominant_failure_message(case_failure_messages),
              }
            }
          }
        }
        return
      }
      generation_error =
        e instanceof Error ? e.message : "Multi-turn generation failed."
    } finally {
      generation_loading = false
    }
  }

  // Mint one test input per approved prompt, locally on the input-generator
  // lane — the same batch-job endpoints the /generate Kiln Pro flow
  // executes its plan with. Returns the inputs as strings (structured-task
  // inputs as JSON strings — the encoding the pipeline and the saved eval's
  // items both use); a prompt whose generation failed is dropped, like the
  // multi-turn arm's upstream salvage, and surfaces in the stop banner's
  // survivor accounting. Throws on job-level failure or zero survivors.
  async function mint_inputs_from_plan(
    approved_prompts: string[],
    input_gen: ModelChoice,
    data_guide: string | null,
    signal: AbortSignal,
  ): Promise<string[]> {
    minting_total = approved_prompts.length
    minting_done = 0
    const start = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/generate_inputs_batch",
      {
        params: { path: { project_id, task_id } },
        body: {
          prompts: approved_prompts,
          // The same grounding guide the plan was drafted under, so the
          // minted inputs match the dataset's real format and voice — and
          // the cache key above can't drift from what actually minted.
          data_guide,
          run_config_properties: {
            type: "kiln_agent" as const,
            model_name: input_gen.model_name,
            model_provider_name: input_gen.model_provider,
            // Input generation runs its own purpose-built prompt server-side
            // and the sampling knobs are the datamodel defaults; these
            // fields just complete the run-config shape.
            prompt_id: "simple_prompt_builder",
            structured_output_mode: "default" as const,
            top_p: 1.0,
            temperature: 1.0,
          },
        },
        signal,
      },
    )
    if (start.error || !start.data) {
      throw new KilnError(
        `Couldn't start writing the test inputs: ${createKilnError(start.error).getMessage()}`,
      )
    }
    const job_id = start.data.job_id
    // Poll the job (the /generate flow's pattern — the batch runs
    // server-side; the client only reads progress).
    for (;;) {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/generate_inputs_batch/{job_id}",
        { params: { path: { project_id, task_id, job_id } }, signal },
      )
      if (error || !data) {
        throw new KilnError(
          `Lost track of the input-writing job: ${createKilnError(error).getMessage()}`,
        )
      }
      minting_done = data.completed
      if (data.status === "error") {
        throw new KilnError(
          `Writing the test inputs failed: ${data.error_message ?? "unknown error"}`,
        )
      }
      if (data.status === "complete") {
        // A blank string is a failed mint too (the pipeline route rejects a
        // request carrying one, and running the task on nothing would be
        // meaningless) — dropped under the same salvage posture as an
        // errored generation. Each failure's message feeds the stop
        // banner's dominant-error diagnosis.
        const inputs = data.results
          .filter(
            (r) =>
              r.input !== null &&
              r.input !== undefined &&
              (typeof r.input !== "string" || r.input.trim() !== ""),
          )
          .map((r) =>
            typeof r.input === "string" ? r.input : JSON.stringify(r.input),
          )
        for (const r of data.results) {
          if (r.error) case_failure_messages.push(r.error)
        }
        if (inputs.length === 0) {
          throw new KilnError(
            "None of the test inputs could be written. Try again.",
          )
        }
        return inputs
      }
      await new Promise((resolve) => setTimeout(resolve, 750))
      if (signal.aborted) {
        throw new DOMException("aborted", "AbortError")
      }
    }
  }

  // Step 4 (single-turn) part 2 — run from the approved plan: mint one test
  // input per approved prompt (local, input-generator lane), then a single
  // single_turn_pipeline stream runs [run → judge] per input — the task
  // executes once per input with tools live on the user's keys.
  async function on_drive_single_turn() {
    // The plan surface's primary button calls this directly, so guard
    // reentry: a double-click during lane resolution must not start a
    // second concurrent pipeline.
    if (generation_loading) return
    if (!batch_plan || batch_plan.prompts.length === 0) {
      generation_error = "No approved inputs. Draft a plan first."
      return
    }
    // Lanes uncommitted (internal re-run path reached before any settings
    // submit) — ask, don't guess.
    const chosen_input_gen = input_generator
    const chosen_judge_model = judge_model
    if (!chosen_input_gen || !chosen_judge_model) {
      open_drive_settings()
      return
    }
    const approved_prompts = batch_plan.prompts
    generation_loading = true
    generation_error = null
    // Clear a previous run's stop banner up front: authoring can fail
    // before the post-preflight clear, and its error must not render
    // alongside a stale stop screen.
    drive_stop = null
    generation_phase = "preflight"
    // Set once the run's batch bookkeeping is committed; the abort
    // handler must leave the previous results untouched before that point.
    let drive_committed = false

    try {
      // 1. Resolve target_run_config (task default → first config). The
      // pipeline runs the task with the saved config verbatim by id, so
      // model, prompt, sampling, and TOOLS all match a manual run.
      const drive_config = await resolve_drive_run_config()
      if (!drive_config) return
      const target_run_config_id = drive_config.id

      // 2. The judge, authored BEFORE the pipeline so the preflight covers
      // its lane too. The server frames the rubric for single-turn from the
      // task's turn mode; the per-spec cache makes re-runs free. A user
      // abort during it cancels the whole run.
      generation_phase = "authoring_judge"
      const authored = await author_judge_prompt_for_spec(
        new_copilot_abort_signal(),
      )
      const judge: JudgeConfig = {
        prompt: authored,
        model_name: chosen_judge_model.model_name,
        model_provider: chosen_judge_model.model_provider,
      }
      generation_phase = "preflight"

      // 3. Preflight ALL THREE lanes concurrently before anything runs or
      // is discarded: a dead key/model stops the run here — before the
      // minting spend and the batch's task/judge spend — on the same stop
      // screen, with the previous run's results (if any) left intact.
      const preflight_failure = await preflight_lanes(
        [
          {
            lane: "run config",
            model_name: drive_config.model_name,
            model_provider: drive_config.model_provider,
          },
          {
            lane: "input generator",
            model_name: chosen_input_gen.model_name,
            model_provider: chosen_input_gen.model_provider,
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

      // 4. Preflight passed. Mint the test inputs BEFORE committing to a
      // run shape: the drive plan below compares them to the current batch
      // to pick top-off vs fresh, and a minting failure here leaves the
      // previous run's results intact. Their generation depends only on
      // the plan, the input-generator model, and the grounding guide —
      // never the run config — so a re-run with all byte-unchanged (the
      // fix-config-then-run-again recovery loop) reuses the cached inputs
      // instead of re-paying one generation call per prompt. Any plan edit
      // or new plan misses the cache.
      const mint_data_guide = grounding_data_guide(grounding_sample)
      let inputs = reusable_minted_inputs(
        cached_minted_inputs,
        approved_prompts,
        chosen_input_gen.model_name,
        chosen_input_gen.model_provider,
        mint_data_guide,
      )
      if (inputs) {
        posthog.capture("eval_v2_minted_inputs_reused", {
          num_inputs: inputs.length,
        })
      } else {
        generation_phase = "minting_inputs"
        inputs = await mint_inputs_from_plan(
          approved_prompts,
          chosen_input_gen,
          mint_data_guide,
          new_copilot_abort_signal(),
        )
        // Cache only a COMPLETE mint: a partial set cached against the full
        // prompt list would make the stop banner's "run the batch again"
        // recovery reuse the same shortfall forever instead of re-minting
        // the failures.
        if (inputs.length === approved_prompts.length) {
          cached_minted_inputs = {
            prompts_json: JSON.stringify(approved_prompts),
            model_name: chosen_input_gen.model_name,
            model_provider: chosen_input_gen.model_provider,
            data_guide: mint_data_guide,
            inputs,
          }
        }
      }

      // 5. The drive plan: TOP OFF the current batch — run only the
      // missing slots, into the same batch tag, keeping the paid
      // successes — when the batch ran these exact inputs under the same
      // judge; otherwise a fresh batch under replace semantics.
      const judge_unchanged = drive_lanes_unchanged({
        judge,
        batch_judge: review_judge,
      })
      const drive_plan = plan_drive({
        items: inputs,
        batch_items: judge_unchanged ? batch_inputs : null,
        built_slots: built_by_case,
        batch_tag: single_turn_batch_tag,
        undeleted_batch_tags,
      })
      if (drive_plan.top_off) {
        posthog.capture("eval_v2_drive_top_off", {
          num_missing: drive_plan.items.length,
        })
      }

      // 6. Commit. On a fresh run every undeleted previous batch is
      // superseded from here (the pipeline deletes their runs once this
      // one has produced replacements) and the slate resets; a top-off
      // keeps the batch's results and bookkeeping — it only fills holes.
      const previous_batch_tag = single_turn_batch_tag
      const previous_batch_inputs = batch_inputs
      const previous_built_by_case = built_by_case
      // The judge/identity stamps roll back with the results: a
      // nothing-driven run restores the previous batch, and the stamps
      // must keep describing the verdicts on screen.
      const previous_review_judge = review_judge
      const previous_reviewed_identity = reviewed_identity
      if (!drive_plan.top_off) {
        trace_claims = []
        trace_reviews = []
        selected_trace_indices = []
        batch_inputs = inputs
        // Failed generations drop their input (the salvage posture): the
        // batch's slot count is what actually minted, not the plan size.
        built_by_case = new Array(inputs.length).fill(null)
        driven_prompts_json = JSON.stringify(approved_prompts)
      }
      pipeline_total_cases = drive_plan.items.length
      reset_pipeline_counters()
      // A fresh run means fresh results — and a top-off adds some — so the
      // loop starts over either way.
      reset_calibration_state()
      drive_committed = true

      // 7. Remember the judge (the ONE JudgeConfig shape used by review and
      // save alike) and identity BEFORE the pipeline runs so save can
      // verify nothing changed under the results.
      review_judge = judge
      reviewed_identity = spec_text()

      // 8. One SSE stream runs the whole pipeline: [run → judge] per input.
      // POST endpoint, so fetch + shared SSE reader (EventSource is
      // GET-only).
      generation_phase = "running_pipeline"
      const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval_builder/single_turn_pipeline`
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          inputs: drive_plan.items,
          input_model_name: chosen_input_gen.model_name,
          input_provider: chosen_input_gen.model_provider,
          target_run_config_id,
          // A top-off runs into the existing batch's tag; null lets the
          // server mint a fresh one.
          batch_tag: drive_plan.batch_tag,
          replace_batch_tags: drive_plan.replace_batch_tags,
          judge,
        }),
        signal: new_copilot_abort_signal(),
      })

      if (!response.ok || !response.body) {
        // The banner speaks plain language; the route and status code are
        // debugging detail, so they go to the console only.
        const detail = await error_detail(response)
        console.error(
          `single_turn_pipeline failed (${response.status}): ${detail}`,
        )
        generation_error = eval_data_error(detail)
        return
      }

      // Results fill the batch's slots as case_judged events arrive (cases
      // complete out of order); a top-off's stream indices map back to
      // their batch slots, so its results land beside the kept ones.
      let any_case_driven = false
      // Set by a batch_aborted frame: a config-scoped judge failure aborted
      // the batch server-side. Cases judged before it remain valid.
      let batch_abort: { error: string; stage: string } | null = null
      // Set by the batch_completed frame — the server's ONLY signal that
      // the run stage finished cleanly and the superseded-batch delete
      // actually ran (a failed/aborted stream tears down before it).
      let batch_completed = false
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
          single_turn_batch_tag = event.batch_tag
        } else if (event.type === "case_driven") {
          any_case_driven = true
          // Runs exist on disk under this batch's tag from here on —
          // record it immediately so an abort can't orphan the batch.
          if (
            single_turn_batch_tag &&
            !undeleted_batch_tags.includes(single_turn_batch_tag)
          ) {
            undeleted_batch_tags = [
              ...undeleted_batch_tags,
              single_turn_batch_tag,
            ]
          }
        } else if (event.type === "case_judged") {
          // Claims stay unbuilt here — they're built lazily (build_claims)
          // for the traces the review surfaces or the user opens. The
          // per-batch tag + slot make the trace id unique across batches,
          // so a stale claims build from a prior batch can't pass the
          // identity guard and corrupt the trace at the same index; within
          // a batch a top-off reuses its slot's id.
          const slot = drive_plan.slot_of_stream_index[event.case_index]
          if (slot === undefined) {
            console.error(
              `single_turn_pipeline: case_judged for unknown case_index ${event.case_index}`,
            )
          } else {
            built_by_case[slot] = {
              trace_id: `${single_turn_batch_tag}_case_${slot}`,
              leaf_run_id: event.leaf_run_id || null,
              raw_input: event.raw_input,
              raw_output: event.raw_output,
              judge_score: event.judge_score,
              judge_reasoning: event.judge_reasoning,
              claims: null,
              final_judgement: null,
              claims_state: "unbuilt",
              claims_error: null,
              // The run's structured trace (tool calls included) powers
              // the modal's chat rendering; null when the run recorded
              // none.
              trace: event.trace ?? null,
            }
            judged_case_count += 1
          }
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
          // Same sentence as the request-level failure above: the pipeline
          // name is debugging detail, so it goes to the console only.
          console.error(`single_turn_pipeline failed: ${event.message}`)
          generation_error = eval_data_error(event.message)
          break stream_loop
        } else if (event.type === "batch_aborted") {
          posthog.capture("eval_v2_pipeline_batch_aborted", {
            stage: event.stage,
          })
          // Keep draining: results that raced past the abort frame are
          // still valid survivors; the server ends the stream right after.
          batch_abort = { error: event.error, stage: event.stage }
        } else if (event.type === "batch_completed") {
          batch_completed = true
        }
        // The `complete` terminator ends the loop.
      }
      if (any_case_driven) {
        if (batch_completed) {
          // batch_completed is the server's guarantee that the superseded
          // batches were deleted — only now are their runs gone. A failed
          // or aborted stream never reaches that delete, so its tags ride
          // to the next run's replace_batch_tags (idempotent, so
          // re-passing an already-deleted tag is harmless).
          undeleted_batch_tags = undeleted_batch_tags.filter(
            (t) => !drive_plan.replace_batch_tags.includes(t),
          )
        }
      } else {
        // Nothing ran: no replacement runs, no deletions — keep pointing
        // at the previous batch (its inputs, slots, and the judge/identity
        // stamps describing its verdicts) so save/cleanup/top-off still
        // work.
        single_turn_batch_tag = previous_batch_tag
        batch_inputs = previous_batch_inputs
        built_by_case = previous_built_by_case
        review_judge = previous_review_judge
        reviewed_identity = previous_reviewed_identity
      }

      // Compact survivors BEFORE any error/warning path: completed verdicts
      // are paid results and must never be discarded by a late failure.
      // Live review entries win over the slots' drive-time copies, so a
      // kept case's built claims survive the compaction.
      const complete = compact_batch_slots(built_by_case, trace_claims)
      if (complete.length > 0) {
        trace_claims = complete
        trace_reviews = build_trace_reviews(complete)
        // The review subset is decided the moment all verdicts are in —
        // the same deterministic judge-stratified pick as multi-turn, so
        // both classes calibrate.
        selected_trace_indices = select_review_subset(complete)
      }
      if (generation_error) return
      if (batch_abort) {
        drive_stop = {
          survivors: complete.length,
          failed: approved_prompts.length - complete.length,
          dominant_error: null,
          aborted_error: batch_abort.error,
        }
        return
      }
      // Failures reaching here are TERMINAL — transient errors were already
      // retried server-side. A clean batch auto-advances silently; ANY
      // shortfall vs the approved plan (minting drops included) stops once
      // on the plan screen with the outcome and the recovery choice.
      const failed = approved_prompts.length - complete.length
      if (failed > 0) {
        drive_stop = {
          survivors: complete.length,
          failed,
          dominant_error: dominant_failure_message(case_failure_messages),
        }
        return
      }
      // Clean batch: hold the progress screen while the claims build, then
      // advance to a fully-loaded review.
      start_claims_gate()
    } catch (e) {
      if (is_abort_error(e)) {
        // A user abort mid-stream leaves whatever cases completed as paid
        // results on disk. Once the run was committed, compact them so
        // they stay visible, and restore the stop banner when the batch is
        // short — without it the retry (top-off) affordance is unreachable
        // from the accepted-data screen. Pre-commit aborts touched nothing.
        if (drive_committed) {
          const complete = compact_batch_slots(built_by_case, trace_claims)
          if (complete.length > 0) {
            trace_claims = complete
            trace_reviews = build_trace_reviews(complete)
            selected_trace_indices = select_review_subset(complete)
            const failed = approved_prompts.length - complete.length
            if (failed > 0) {
              drive_stop = {
                survivors: complete.length,
                failed,
                dominant_error: dominant_failure_message(case_failure_messages),
              }
            }
          }
        }
        return
      }
      generation_error =
        e instanceof Error ? e.message : "Single-turn generation failed."
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
    // No plan → plan; otherwise (re)drive the approved plan. A re-drive
    // passes the previous batch tags so their runs are deleted server-side.
    if (batch_plan === null) {
      on_plan_batch()
    } else if (is_multi_turn) {
      on_drive_multi_turn()
    } else {
      void on_drive_single_turn()
    }
  }

  // Advance from the Refine step (3) into Generate (4). Both arms plan
  // immediately (planning needs no model choice); an existing plan renders
  // for re-approval instead. Model choices are confirmed on the plan
  // screen — run-immediately with defaults, or the settings link.
  function on_advance_to_generate() {
    goto_step("generate")
    if (batch_plan === null) on_plan_batch()
  }

  // Same pattern for Review (5) → Save (6): land on Save with the request
  // already in flight; only show the in-step button on error as retry.
  // Both arms first route through the calibration loop: a review with
  // disagreement enters a refine+re-check round instead of saving, round
  // after round, until the grades converge (or the user opts out via the
  // save-without-refining link under the CTA). A judge the reviewer said was
  // wrong never ships without them seeing it re-checked.
  function on_advance_to_save() {
    const graded = build_graded_traces(trace_claims, trace_reviews)
    const decision = plan_save_action({
      has_disagreement: has_grade_disagreement(graded),
    })
    if (decision.action === "calibrate") {
      void run_calibration_round()
      return
    }
    // Converged: zero disagreement, so the judge whose verdicts were just
    // graded (the last refined one) ships through the normal save.
    if (calibration_rounds_completed > 0) {
      posthog.capture("eval_v2_judge_calibration_converged", {
        is_multi_turn,
        rounds: calibration_rounds_completed,
      })
    }
    goto_step("save")
    on_save()
  }

  // ── Step 5 state — Claim/Evidence review.
  // Generated traces are distilled into claims (per-trace server claim builder)
  // that the reviewer agrees/disagrees with; the trace stays hidden in a modal.
  let trace_claims: TraceClaims[] = []
  let trace_reviews: TraceReview[] = []
  // Which traces the reviewer is asked to review (indices into trace_claims):
  // a judge-stratified subset on both arms. The review surfaces exactly this
  // subset — unselected traces are not shown; they land in the train split
  // unrated.
  let selected_trace_indices: number[] = []
  // Save gate (both arms): the human-rated golden answer key caps at 25% of
  // the batch runs server-side, so the reviewer must rate at least N//4
  // traces — reviewing more is welcome, fewer starves the answer key.
  // Calibration rounds cap the demand at the round's actual subset size: a
  // re-judge shortfall can surface fewer traces than the standard target,
  // and the gate must never demand reviews of traces it didn't show.
  $: review_target_count =
    calibration_rounds_completed > 0
      ? calibration_gate_target(
          trace_claims.length,
          selected_trace_indices.length,
        )
      : review_target(trace_claims.length)
  $: reviewed_count = reviewed_trace_count(trace_claims, trace_reviews)
  $: save_gate_met =
    trace_claims.length > 0 && reviewed_count >= review_target_count
  // The review CTA says what clicking it does: with any graded disagreement
  // a save enters a refine round, so the button reads Refine Judge (with a
  // tooltip naming the count). It flips back to Save the moment the last
  // disagreement clears — the convergence signal. Uses the loop's exact entry
  // predicate, so label and behavior can't drift apart.
  $: review_disagreement_count = grade_disagreement_count(
    build_graded_traces(trace_claims, trace_reviews),
  )
  $: review_cta_state = review_cta({
    num_disagreements: review_disagreement_count,
  })
  // The arm's word for one reviewed item, for copy that counts them.
  $: judged_noun = is_multi_turn ? "conversation" : "example"
  // The arm's words for the plan's rows and one unit of drive work — the
  // step-4 surfaces (plan screen, confirms, stop banner) count in these.
  $: plan_noun = is_multi_turn ? "scenarios" : "planned inputs"
  $: case_noun = is_multi_turn ? "conversation" : "test run"
  // Bound out of the review component: true only while it shows its last
  // trace, which is where it renders the primary CTA. The save-without-
  // refining link stacks under that CTA, so it follows this flag.
  let review_on_last_trace = false

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
  // fully loaded: Previous can revisit any earlier trace, so every selected
  // claim set must be resolved before the review opens, not just the first.
  // Errored builds don't hold the door — they keep their in-review
  // error+retry card.
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
    // PUSH review (both arms): Back must return to the plan screen.
    goto_step("review")
  }

  // The review component reports the trace it's showing (also its retry
  // affordance) — build that trace's claims if they aren't underway.
  function on_open_trace(index: number) {
    void build_claims_for_index(index)
  }

  // ── Judge calibration loop (both arms). A save with disagreement never
  // ships a judge the reviewer hasn't seen judge: it refines EXPLICITLY,
  // re-checks the eval data with the refined prompt, and asks the reviewer to
  // grade the result — round after round. Both arms re-judge their driven
  // runs by durable id (judge_traces) and re-open a smart-picked subset.
  // Save happens only when a review carries zero disagreement (the judge
  // that ships is the one whose verdicts were graded) or when the user opts
  // out via the save-without-refining link under the review CTA.
  type CalibrationPhase = "idle" | "refining" | "rejudging" | "building_claims"
  let calibration_phase: CalibrationPhase = "idle"
  // Completed refine+re-judge rounds this batch — round tags, the gate
  // target, and convergence telemetry all key off it.
  let calibration_rounds_completed = 0
  // Retryable round failure (the re-check stream died); Retry resumes at
  // the re-check without re-paying the refine call.
  let calibration_error: string | null = null
  // Refine-attempt failure (request died, timeout, unusable prompt): shown
  // inline under the review actions. The CTA stays Refine Judge and re-fires
  // the refine; the save-without-refining link remains the way out.
  let calibration_refine_error: string | null = null
  // Cases without a fresh verdict last round — surfaced honestly above the
  // review; they keep stale results and sit the round out.
  let calibration_failed_count = 0
  // Durable run ids of traces graded in ANY round — the fresh top-up must
  // never re-serve them as "never reviewed".
  let calibration_reviewed_keys = new Set<string>()
  // The refined judge awaiting a successful re-check, plus the disagreement
  // snapshot it was refined from — kept so a Retry resumes here.
  let calibration_pending_judge: JudgeConfig | null = null
  let calibration_pending_disagreed: number[] = []
  // Live re-check progress (the pipeline progress surface, without the
  // drive): re-judged case counts off the judge_traces stream.
  let rejudged_done = 0
  let rejudge_failed_live = 0
  let rejudge_total = 0

  // Fresh batch, fresh loop: a new multi-turn plan or drive, or a new
  // single-turn generation, invalidates every round counted before it.
  function reset_calibration_state() {
    calibration_phase = "idle"
    calibration_rounds_completed = 0
    calibration_error = null
    calibration_refine_error = null
    calibration_failed_count = 0
    calibration_reviewed_keys = new Set()
    calibration_pending_judge = null
    calibration_pending_disagreed = []
    rejudged_done = 0
    rejudge_failed_live = 0
    rejudge_total = 0
  }

  // The readable reason from a failed streaming response. The error handler
  // wraps detail as {message}; typed route errors nest {code, message} inside
  // it — unwrap either shape so a retry surface says what to fix.
  async function error_detail(response: Response): Promise<string> {
    try {
      const err_json = await response.json()
      const message = err_json?.message
      return (
        (typeof message === "string" ? message : message?.message) ??
        err_json?.detail?.message ??
        "unknown"
      )
    } catch {
      return await response.text().catch(() => "unknown")
    }
  }

  // The banner sentence for a failed generation. A detail we couldn't read
  // ("unknown" or empty) says nothing to the user, so the colon clause is
  // dropped entirely rather than trailing a placeholder.
  function eval_data_error(detail: string): string {
    const readable = detail.trim()
    if (readable === "" || readable === "unknown")
      return "Could not create your eval data."
    return `Could not create your eval data: ${readable}`
  }

  // Refine the judge from the current grades. It does NOT fall back: any
  // failure or unusable prompt throws to the inline refine error, because
  // silently keeping the old judge would re-run the review the user just did
  // and call it improvement. A user abort propagates.
  class CalibrationRefineError extends Error {
    reason: string
    constructor(reason: string, message: string) {
      super(message)
      this.reason = reason
    }
  }

  async function refine_judge_for_calibration(
    judge: JudgeConfig,
  ): Promise<JudgeConfig> {
    const graded_traces = build_graded_traces(trace_claims, trace_reviews)
    const { signal, timed_out } = with_deadline(
      new_copilot_abort_signal(),
      JUDGE_COPILOT_DEADLINE_MS,
    )
    let data, error
    try {
      ;({ data, error } = await client.POST(
        "/api/projects/{project_id}/tasks/{task_id}/eval_builder/refine_judge",
        {
          params: { path: { project_id, task_id } },
          body: { judge_prompt: judge.prompt, graded_traces },
          signal,
        },
      ))
    } catch (e) {
      if (timed_out()) {
        throw new CalibrationRefineError(
          "timeout",
          "Refining the judge took too long.",
        )
      }
      if (is_abort_error(e)) throw e
      throw new CalibrationRefineError(
        "request_failed",
        "Couldn't reach the server to refine the judge.",
      )
    }
    if (error || !data) {
      throw new CalibrationRefineError(
        "request_failed",
        createKilnError(error).getMessage(),
      )
    }
    const proposal = data as RefineJudgeProposal
    const validation_error = validate_refined_judge_prompt(
      proposal.refined_judge_prompt,
    )
    if (validation_error) {
      throw new CalibrationRefineError(
        "invalid_refined_prompt",
        "The refined judge prompt wasn't usable.",
      )
    }
    return { ...judge, prompt: proposal.refined_judge_prompt }
  }

  // Re-judge every driven case with the refined judge over the judge_traces
  // stream (both arms — the server reloads each run by id and applies the
  // arm's judge reading). Returns fresh verdicts keyed by trace index; cases
  // that failed to re-judge are simply absent. Throws on stream-level
  // failure (bad response, batch_failed, batch_aborted, or nothing judged) —
  // partial results from a broken stream are never applied.
  async function rejudge_all_traces(
    judge: JudgeConfig,
  ): Promise<Map<number, RejudgeCaseResult>> {
    // Every driven case with a durable run id, in plan order. The runner
    // emits "" for a run without an id — such a case can't be reloaded, so
    // it sits the round out like a failed case.
    const entries = trace_claims
      .map((tc, i) => ({ i, id: tc.leaf_run_id }))
      .filter((e): e is { i: number; id: string } => Boolean(e.id))
    if (entries.length === 0) {
      throw new KilnError(
        `None of the ${case_noun}s have saved ids to re-check. Create your eval data again.`,
      )
    }
    rejudge_total = entries.length
    rejudged_done = 0
    rejudge_failed_live = 0
    const url = `${base_url}/api/projects/${project_id}/tasks/${task_id}/eval_builder/judge_traces`
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        leaf_run_ids: entries.map((e) => e.id),
        judge,
      }),
      signal: new_copilot_abort_signal(),
    })
    if (!response.ok || !response.body) {
      throw new KilnError(
        `Re-checking your eval data failed (${response.status}): ${await error_detail(response)}`,
      )
    }
    const results = new Map<number, RejudgeCaseResult>()
    let batch_abort: string | null = null
    let batch_fail: string | null = null
    const reader = response.body.getReader()
    stream_loop: for await (const payload of sse_data_payloads(reader)) {
      if (payload === "complete") break
      let event: PipelineEvent
      try {
        event = JSON.parse(payload) as PipelineEvent
      } catch {
        continue
      }
      if (event.type === "case_judged") {
        // case_index is the position in the request's leaf_run_ids — map it
        // back to the trace index it came from.
        const entry = entries[event.case_index]
        if (!entry) continue
        results.set(entry.i, {
          judge_score: event.judge_score,
          judge_reasoning: event.judge_reasoning,
          raw_input: event.raw_input,
          raw_output: event.raw_output,
          trace: event.trace ?? null,
        })
        rejudged_done += 1
      } else if (event.type === "case_failed") {
        rejudge_failed_live += 1
      } else if (event.type === "batch_aborted") {
        // Keep draining: the server ends the stream right after, and any
        // frames racing the abort still count toward the honest diagnosis.
        batch_abort = event.error
      } else if (event.type === "batch_failed") {
        batch_fail = event.message
        break stream_loop
      }
    }
    if (batch_fail) {
      throw new KilnError(`Re-checking your eval data failed: ${batch_fail}`)
    }
    if (batch_abort) {
      throw new KilnError(`Re-checking your eval data stopped: ${batch_abort}`)
    }
    if (results.size === 0) {
      throw new KilnError(
        `None of the ${case_noun}s could be re-checked. Try again.`,
      )
    }
    return results
  }

  // One calibration round: refine → re-check the eval data → re-grade against
  // the refined judge's verdicts. Every grade resets (a refined judge can flip
  // previously-agreed verdicts too, and nothing unseen ships). Both arms then
  // smart-pick a new subset and wait on a claims rebuild. `resume` restarts
  // at the re-check with the already-refined judge (the Retry path).
  async function run_calibration_round(resume = false) {
    if (calibration_phase !== "idle") return
    calibration_error = null
    calibration_refine_error = null
    const round = calibration_rounds_completed + 1
    const base_judge = review_judge
    if (!base_judge) {
      // There is no judge to refine FROM — the review on screen was never
      // pinned to one. Report it on the inline refine surface (the same
      // sentence save uses for the same missing judge) rather than returning
      // quietly, which would leave the CTA doing nothing however often it is
      // clicked.
      calibration_refine_error =
        "No judge was configured. Go back and re-run the review."
      return
    }
    try {
      let refined = resume ? calibration_pending_judge : null
      let disagreed = resume ? calibration_pending_disagreed : []
      if (!refined) {
        // Snapshot who was reviewed and who was disagreed with BEFORE the
        // grades reset — the smart pick prioritizes the disagreements and
        // the fresh top-up excludes everyone already graded.
        disagreed = disagreed_trace_indices(trace_reviews)
        trace_claims.forEach((tc, i) => {
          if (tc.leaf_run_id && is_trace_reviewed(tc, trace_reviews[i])) {
            calibration_reviewed_keys.add(tc.leaf_run_id)
          }
        })
        posthog.capture("eval_v2_judge_calibration_round_started", {
          is_multi_turn,
          round,
          num_disagreements: disagreed.length,
        })
        calibration_phase = "refining"
        refined = await refine_judge_for_calibration(base_judge)
        calibration_pending_judge = refined
        calibration_pending_disagreed = disagreed
      }
      calibration_phase = "rejudging"
      const results = await rejudge_all_traces(refined)
      const flipped = flipped_indices(trace_claims, results)
      // Compute the whole round outcome BEFORE committing any of it, so a
      // round that can't produce a review leaves grades and verdicts intact.
      const applied = apply_rejudge_results(
        trace_claims,
        results,
        `${is_multi_turn ? multi_turn_batch_tag : single_turn_batch_tag}_r${round}`,
      )
      const reviewed = applied
        .map((tc, i) => ({ tc, i }))
        .filter(
          ({ tc }) =>
            tc.leaf_run_id && calibration_reviewed_keys.has(tc.leaf_run_id),
        )
        .map(({ i }) => i)
      const subset = select_calibration_subset(applied, {
        disagreed,
        flipped,
        reviewed,
        judged: [...results.keys()],
      })
      if (subset.length === 0) {
        // Zero eligible traces (every re-judged trace already reviewed, the
        // rest failed): a review round with nothing to review would wedge
        // the gate. Fail the round on the retryable surface instead; Retry
        // resumes at the re-judge, same as a stream failure.
        throw new KilnError(
          `None of the re-checked ${case_noun}s could be selected for review. Try again.`,
        )
      }
      calibration_failed_count = trace_claims.length - results.size
      posthog.capture("eval_v2_judge_calibration_round_completed", {
        is_multi_turn,
        round,
        num_flips: flipped.length,
        num_judged: results.size,
        num_failed: calibration_failed_count,
      })
      // Fold the fresh verdicts in and rebuild the review state around
      // them: every grade resets, the save gate re-arms, and the reviewer
      // grades the refined judge's output — which is why the refined judge
      // becomes review_judge (save persists the judge the review graded).
      trace_claims = applied
      trace_reviews = build_trace_reviews(applied)
      review_judge = refined
      selected_trace_indices = subset
      calibration_rounds_completed = round
      calibration_pending_judge = null
      calibration_pending_disagreed = []
      // Hold a progress screen while the new subset's claims build against
      // the fresh verdicts, so the re-review opens fully loaded (the same
      // wait-for-all contract as the first round's claims gate).
      calibration_phase = "building_claims"
      prefetch_selected_claims()
    } catch (e) {
      calibration_phase = "idle"
      if (is_abort_error(e)) return
      if (e instanceof CalibrationRefineError) {
        posthog.capture("eval_v2_judge_calibration_refine_failed", {
          is_multi_turn,
          round,
          reason: e.reason,
        })
        // Surface the failure inline under the review actions. The grades
        // stay editable underneath it, so clicking Refine Judge again starts
        // a fresh attempt from whatever the grades say at that moment.
        // Bare message, data-guide idiom: the Refine Judge CTA above it and
        // the bail link below already say what the user can do.
        calibration_refine_error = e.message
        return
      }
      calibration_error =
        e instanceof Error ? e.message : "Re-checking your eval data failed."
    }
  }

  // The round's claims gate: once every selected trace resolved (built or
  // errored), open the re-review. Same wait-for-all rule as the first-round
  // gate; errored builds keep their in-review retry card.
  $: if (
    calibration_phase === "building_claims" &&
    selected_trace_indices.length > 0 &&
    selected_claims_resolved === selected_trace_indices.length
  ) {
    calibration_phase = "idle"
  }

  // The loop's opt-out (the link under the review CTA): save immediately
  // with the judge whose verdicts the reviewer actually graded — the latest
  // refined one once a round has run — grades carried as-is.
  function save_without_refining() {
    posthog.capture("eval_v2_judge_calibration_opted_out", {
      is_multi_turn,
      rounds: calibration_rounds_completed,
      num_disagreements: review_disagreement_count,
      // Whether a refine failure was on screen when they bailed: bailing out
      // of a broken refine is a different signal from bailing out of a loop
      // that simply wasn't converging.
      refine_error_shown: calibration_refine_error !== null,
    })
    calibration_refine_error = null
    goto_step("save")
    on_save()
  }

  // ── The staleness gate (non-destructive). Results judged under an old
  // spec text are stale — the judge prompt was authored from that text and
  // every graded claim argues it — but stale-relative-to-an-edit is not
  // invalid: reverting the edit makes them exactly as good as before. So a
  // mismatch BLOCKS the review render (below) instead of clearing anything;
  // results are discarded only by the explicit action, a re-drive, or a new
  // plan. Derived (not checked at a transition) so browser Forward can't
  // slip into a stale review either.
  $: review_results_stale =
    trace_claims.length > 0 &&
    reviewed_identity !== null &&
    reviewed_identity !== current_spec_text

  // The gate's explicit way out: throw the results away and return to the
  // plan screen to re-create under the edited description. history.back()
  // (not replace_step) because the gate's review entry was PUSHED over the
  // plan screen — replacing would leave two adjacent generate entries and a
  // dead first Back press.
  function discard_stale_results() {
    const msg = driven_data_confirm(
      "Discarding",
      trace_claims.length,
      drive_stop === null,
    )
    if (!confirm(msg)) return
    discard_driven_results()
    history.back()
  }

  // Generation → review: advance to existing results, re-driving when
  // needed. Pushes (not replaces) so Back from review returns here — this
  // path is only reachable when Step 4 has real content to come back to.
  function continue_to_review() {
    if (review_results_stale) {
      // Land on the review step, where the gate renders instead of the
      // review: it explains the mismatch and offers revert-or-discard.
      // Nothing is cleared here — a revert restores the review as-is.
      goto_step("review")
      return
    }
    if (trace_claims.length === 0) {
      // Nothing to show (a Back aborted the pipeline) — re-drive.
      if (is_multi_turn) {
        on_drive_multi_turn()
      } else {
        void on_drive_single_turn()
      }
      return
    }
    // Claims are lazy on both arms — gate the advance on the selected
    // traces being fully resolved (instant when already built).
    start_claims_gate()
  }

  // ── Step 6 state — save
  let saving = false
  let save_error: string | null = null

  async function on_save() {
    saving = true
    save_error = null
    try {
      if (reviewed_identity !== spec_text()) {
        // Backstop for the staleness gate: the gate blocks the review
        // render, but save must independently refuse to persist a judge
        // calibrated against different spec text.
        save_error =
          "The eval's description changed since the review. Go back and revert it, or create your eval data again."
        return
      }
      // Source of truth for the saved spec is refined_property_values —
      // populated from Step 1 description initially, then updated in Step 3
      // when the user accepts or edits the proposed refinements. Fall back
      // to property_values if Step 3 was skipped (no refinements were
      // proposed). spec_text() applies the same precedence, so the saved
      // definition equals what generation/review saw.
      // The fallback filters to rendered fields like every other path, so
      // classifier-authored example values can never reach the saved spec.
      const final_values =
        Object.keys(refined_property_values).length > 0
          ? refined_property_values
          : keep_rendered_fields(property_values, RENDERED_REFINE_FIELDS)
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

      // The judge to persist = the judge the review ran (review_judge).
      // Deliberately NO fallback or static-template last resort: silently
      // persisting a generic judge is the one thing save must never do.
      const review_judge_config = review_judge
      if (!review_judge_config) {
        save_error = "No judge was configured. Go back and re-run the review."
        return
      }
      // What ships is exactly the judge whose verdicts the reviewer graded.
      // Both arms refine in the calibration loop, where the refined judge is
      // re-checked and re-graded before it can reach save — so there is no
      // late rewrite the reviewer never saw.
      const save_judge = review_judge_config

      // Multi-turn save: golden/train tags land on the driven chains; the
      // eval slice is minted server-side as EvalInputs from the driven cases.
      if (is_multi_turn) {
        if (multi_turn_batch_tag === null || driven_cases.length === 0) {
          save_error = "No multi-turn chains were generated. Go back to Step 4."
          return
        }
        // The saved batch's own tag: its chains become the eval, so it must
        // be excluded from any future cleanup (below).
        const saved_batch_tag = multi_turn_batch_tag
        // The synthetic-user model the chains were actually driven with,
        // captured at batch commit — missing means no drive happened.
        const saved_su_driver = driven_su_driver
        if (saved_su_driver === null) {
          save_error =
            "No simulated-user model was recorded. Go back to Step 4."
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
              judge_info: save_judge,
              multi_turn: {
                batch_tag: saved_batch_tag,
                reviewed_chains,
                cases: driven_cases,
                // The drive settings this wizard's conversations ran with —
                // stamped onto each minted eval item, so eval-time re-drives
                // replay the same synthetic user (model + turns).
                drive_config: {
                  model_name: saved_su_driver.model_name,
                  model_provider: saved_su_driver.model_provider,
                  turns: TURNS_PER_CASE,
                },
              },
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
        // draft's authoring job is done (a kept draft would restore a stale
        // wizard over the saved eval on the next visit). But earlier aborted
        // drives can have stranded superseded chains on disk; carry only
        // those cleanup tags (never the just-saved batch's) so a later drive
        // on this task deletes them instead of orphaning them forever.
        await clear_builder_draft(
          draft_after_save_keeping_stranded_tags(
            saved_batch_tag,
            undeleted_batch_tags,
          ),
        )
        if (saved.id) {
          leave_guard_suppressed = true
          goto(`/specs/${project_id}/${task_id}/${saved.id}`)
        } else {
          replace_step("done")
        }
        return
      }

      // Single-turn save: golden/train tags and the human's ratings land on
      // the batch-tagged runs the pipeline persisted; the eval slice is
      // minted server-side as inputs-only EvalInputs from the inputs those
      // runs were driven on. Nothing is generated at save time — the
      // dataset IS the runs the user just reviewed.
      if (single_turn_batch_tag === null || trace_claims.length === 0) {
        save_error = "No test runs were generated. Go back to Step 4."
        return
      }
      // The saved batch's own tag: its runs become the eval's dataset, so
      // it must be excluded from any future cleanup (below).
      const saved_batch_tag = single_turn_batch_tag
      // Carry the human's review through save: each reviewed trace maps to
      // its persisted run (leaf_run_id from the pipeline); the studio
      // writes the golden rating + per-claim grades onto that run. Only
      // traces the human actually reviewed ride along (subset review:
      // unreviewed runs land in the train split, unrated).
      const reviewed_runs = trace_claims
        .map((tc, i) => ({ tc, review: trace_reviews[i] }))
        // Truthy check: the pipeline emits "" (not null) when a run has no
        // id — such a run can't be rated, so skip it.
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
            // The pipeline judged final answers, so the saved eval must
            // too (the server refuses a full-trace single-turn save).
            evaluate_full_trace: false,
            judge_info: save_judge,
            single_turn: {
              batch_tag: saved_batch_tag,
              reviewed_runs,
              // The eval slice: the inputs the surviving runs were driven
              // on, byte-identical to what the judge scored (raw_input
              // echoes the request input on every round).
              inputs: trace_claims.map((tc) => tc.raw_input),
            },
            // The auto-picked sample that grounded planning and input
            // minting, recorded on the Spec for provenance (v1 parity).
            task_sample: grounding_sample,
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
        num_cases: trace_claims.length,
      })
      const saved = data as { id?: string }
      // Persisted — same draft retirement as multi-turn: carry only
      // stranded cleanup tags (never the just-saved batch's) so a later
      // run on this task deletes them instead of orphaning them forever.
      await clear_builder_draft(
        draft_after_save_keeping_stranded_tags(
          saved_batch_tag,
          undeleted_batch_tags,
        ),
      )
      if (saved.id) {
        leave_guard_suppressed = true
        goto(`/specs/${project_id}/${task_id}/${saved.id}`)
      } else {
        replace_step("done")
      }
      return
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
  // steps with bespoke buttons. FormContainer-backed steps (clarify) already
  // handle it; skipping them avoids double-firing.
  function handle_global_keydown(event: KeyboardEvent) {
    if (!((event.metaKey || event.ctrlKey) && event.key === "Enter")) return
    // No step is on screen behind the page-level gates (copilot check, task
    // load, task error), so the shortcut must not start work the user can't
    // see — Step 4's forward action spends model calls.
    if ($kilnCopilotConnected !== true || task_loading || task_error) return
    // The settings and trace modals cover the step they open over. A keystroke
    // aimed at an open modal must not reach the page behind it, or the wizard
    // navigates away while the modal is still on screen.
    if (document.querySelector("dialog[open]")) return
    if (current_step === "describe") {
      if (description.trim() && !classifying) {
        event.preventDefault()
        classify_then_continue()
      }
    } else if (current_step === "refine" && !refined_preview_loading) {
      // Same validator gate as the Next button; the in-flight guard lives
      // in on_refine_submit itself.
      if (
        filename_string_short_validator(name) === null &&
        (refined_property_values.issue_description ?? "").trim()
      ) {
        event.preventDefault()
        on_refine_submit()
      }
    } else if (current_step === "generate") {
      // Mirrors the step's own screen states: the keyboard fires whichever
      // forward primary is on screen, and nothing while a stage is running or
      // an error is holding the screen (those offer retry, not forward).
      if (generation_loading || preparing_review) return
      if (show_plan_approval && batch_plan) {
        // The plan surface's own generate button belongs to the shared
        // component and has no keyboard path; only the continue-to-results
        // action beside it is ours to fire.
        if (has_driven_results) {
          event.preventDefault()
          on_continue_with_survivors()
        }
      } else if (!generation_error && !claims_gate_error) {
        event.preventDefault()
        if (trace_claims.length > 0) {
          continue_to_review()
        } else {
          on_plan_batch()
        }
      }
    } else if (current_step === "review") {
      // The gate/last-trace pair matches the Save button only within the review
      // component: the gate can be met several traces early, and the shortcut
      // must not skip traces the reviewer still sees a Next button for. The
      // screen-level guards exclude the stale-results gate, the calibration
      // error screen, and in-flight calibration, where that component is
      // unmounted but its binds still hold their last values.
      if (
        !review_results_stale &&
        !calibration_error &&
        calibration_phase === "idle" &&
        save_gate_met &&
        review_on_last_trace
      ) {
        event.preventDefault()
        on_advance_to_save()
      }
    }
  }

  // Auto-load questions when entering Step 2, and regenerate them when the
  // user went Back and edited the description: the questions on screen were
  // authored against the old text, so they no longer fit the new spec.
  $: if (
    current_step === "clarify" &&
    !questions_are_current(question_set_source, description) &&
    !questions_loading
  ) {
    load_questions()
  }

  // Human name for each authoring step. The AppPage title is a constant
  // ("Eval Builder"); the position + this name are the first subtitle line
  // ("Step N of TOTAL — <name>"), so the wizard's own chrome doesn't need a
  // separate step-indicator row. The done screen keeps its own title instead.
  function step_name_for(step: BuilderStep): string {
    switch (step) {
      case "describe":
        return "Describe your eval"
      case "clarify":
        return "A few questions"
      case "refine":
        return "Check the details"
      case "generate":
        return "Create eval data"
      case "review":
        // Verdict-neutral on purpose: half of every batch passes by design,
        // so a fault-presuming headline would blame agents that behaved —
        // and the reviewer grades the AGENT's work, never the judge.
        return "Grade the results"
      case "save":
        return "Save your eval"
      case "done":
        return "Eval Created"
    }
  }

  // Per-step description, shown under the step line. Lifted to AppPage so the
  // heading lives in the standard page header, matching v1.
  function page_subtitle_for(step: BuilderStep): string | undefined {
    switch (step) {
      case "describe":
        return "Describe a behaviour to enforce or avoid for your task. We'll build your eval from it."
      case "clarify":
        // The Questions component carries its own heading + explainer —
        // a page-level subtitle here would say the same thing twice.
        return undefined
      case "refine":
        return "We've drafted your eval from your answers. Edit anything that's off."
      case "generate":
        return is_multi_turn
          ? "Kiln simulates a user talking to your agent to build your eval's test data."
          : "Kiln plans test inputs, runs your task on each, and judges the results."
      case "review":
        // Multi-turn always reviews on the claims, so its copy can name the
        // flagged mistakes and the citations that locate them. The mistake
        // framing lives at the STEP level, where it's true of the batch (some
        // conversations failed); each conversation's own verdict card says
        // which way that one went. ~Half of every batch passes by design
        // (balanced plan + stratified sample), so the per-conversation
        // surface stays verdict-neutral.
        return is_multi_turn
          ? `A judge reviewed each test conversation in your eval data and flagged possible mistakes. Keep the real ones, dismiss the false alarms. You're reviewing ${review_target_count} of ${trace_claims.length}. Click a citation number to see the moment it happened.`
          : // A single-turn run reviews on the trace itself when it's short
            // enough, and that shape shows no flagged mistakes, no claim
            // cards and no citation numbers until the reviewer has graded.
            // So this copy names none of them: it states what the judge did
            // and what the reviewer does, which holds on either shape.
            `A judge scored every test run in your eval data. You're reviewing ${review_target_count} of ${trace_claims.length}. Check the evidence for each one, then grade it.`
      case "save":
        return "Saving your eval and its test data."
      case "done":
        return undefined
    }
  }

  // v1 widens the layout when there's a side-by-side comparison or table
  // (review). Mirror that here so those tables aren't crammed into a 3xl
  // box.
  function page_max_w_for(step: BuilderStep): string {
    if (step === "review") return "max-w-[1400px]"
    // Generate hosts the plan-approval table (long prompts, both arms) —
    // give it the same wide layout as review.
    if (step === "generate") return "max-w-[1400px]"
    return "max-w-[900px]"
  }

  // The page header title stays "Eval Builder" across the whole wizard,
  // including done: the completion card below owns the outcome heading, so a
  // constant header never shows the outcome twice on the same screen.
  const page_title = "Eval Builder"
  // First subtitle line carries the step position + name. Empty on done AND
  // on save: saving is a transition out of Step 5, not a stop of its own —
  // the header shows just the saving description there.
  $: page_step_line =
    current_step === "done" || current_step === "save"
      ? ""
      : `Step ${STEP_INDEX[current_step]} of ${TOTAL_STEPS}: ${step_name_for(
          current_step,
        )}`
  $: page_subtitle = page_subtitle_for(current_step)
  $: page_max_w = page_max_w_for(current_step)

  // Total assistant turns expected across the whole batch — the denominator
  // for the smooth turn-level progress (cases run in parallel waves, so this
  // climbs steadily where the case count would sit still then jump). Uses
  // the DRIVEN case count: salvage can drive fewer cases than the plan has.
  $: multi_turn_total_turns = pipeline_total_cases * TURNS_PER_CASE

  // Step 4 loading-stage title + caption for the pre-pipeline stages (the
  // pipeline stage has its own progress screen below). One phase machine,
  // arm-specific words for the arm-specific stages.
  $: generate_animation_title =
    generation_phase === "planning"
      ? is_multi_turn
        ? "Drafting Scenarios"
        : "Planning Test Inputs"
      : generation_phase === "authoring_judge"
        ? "Authoring Judge"
        : generation_phase === "preflight"
          ? "Checking Configuration"
          : generation_phase === "minting_inputs"
            ? "Writing Test Inputs"
            : "Creating Simulated Users"
  $: generate_animation_description =
    generation_phase === "planning"
      ? is_multi_turn
        ? `Drafting a balanced set of ${NUM_CASES} scenarios for your eval.`
        : `Drafting a balanced plan of ${NUM_CASES} test inputs for your eval.`
      : generation_phase === "authoring_judge"
        ? "Authoring a judge rubric tailored to your eval."
        : generation_phase === "preflight"
          ? `Checking that your run config, the ${
              is_multi_turn
                ? "model that plays the user"
                : "model that writes the test inputs"
            }, and the judge all respond before creating your eval data.`
          : generation_phase === "minting_inputs"
            ? `Writing ${planned_total} test inputs from the approved plan.`
            : `Setting up ${planned_total} simulated users from the approved scenarios.`

  // The long-wait line, on exactly the stages that run one long request with
  // no progress bar. Stages that show a bar let the bar carry the wait, and
  // preflight is a reachability check measured in seconds, so a wait warning
  // there would set the wrong expectation. Both arms share the rule:
  // generating_cases is multi-turn only, minting_inputs single-turn only.
  $: generate_animation_warning =
    generation_phase === "planning" ||
    generation_phase === "authoring_judge" ||
    generation_phase === "generating_cases"
      ? "This may take a while"
      : null

  // Multi-turn save tags existing chains rather than generating a dataset.
  // The single-turn line is a placeholder: its save currently refuses (the
  // writer is moving onto the locally-run data), so the screen shows the
  // refusal, not this caption.
  $: save_animation_description = is_multi_turn
    ? "Saving your eval and tagging the generated conversations."
    : "Saving your eval."
</script>

<svelte:window
  on:keydown={handle_global_keydown}
  on:beforeunload={handle_before_unload}
/>

<!-- Constrain AppPage (title + body) to page_max_w, matching v1 spec_builder.
     Centring v1's inner content is handled by AppPage's own header/slot
     layout, so no mx-auto here. -->
<div class={page_max_w}>
  <AppPage
    title={page_title}
    subtitle={page_step_line}
    sub_subtitle={page_subtitle ?? ""}
    breadcrumbs={[{ label: "Evals", href: `/specs/${project_id}/${task_id}` }]}
    no_y_padding
    action_buttons={reset_available
      ? [{ label: "Reset", handler: reset_draft_with_confirm }]
      : []}
  >
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
        {#if task_loading}
          <!-- Same page-level loading block as the copilot check above. -->
          <div class="w-full min-h-[50vh] flex justify-center items-center">
            <div class="loading loading-spinner loading-lg"></div>
          </div>
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
            <button class="btn btn-outline" on:click={back_to_task}
              >Cancel</button
            >
            <!-- FormContainer's compact submit spec (wide primary + keyboard
                 hint), hand-rolled because this row isn't a FormContainer.
                 The hint hides while the request is in flight, matching the
                 shared container's submitting state. -->
            <button
              class="relative btn btn-primary min-w-64 px-12"
              on:click={classify_then_continue}
              disabled={!description.trim() || classifying}
            >
              {#if classifying}
                <span class="loading loading-dots loading-sm"></span>
                Classifying…
              {:else}
                Next
                <span class="absolute opacity-80 right-4 text-xs font-light">
                  {#if isMacOS()}
                    <span class="tracking-widest">⌘↵</span>
                  {:else}
                    <span>ctrl ↵</span>
                  {/if}
                </span>
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
              description="Analyzing your criteria for areas that could use more clarity."
            />
          {:else if questions_error}
            <Warning warning_color="error" warning_message={questions_error} />
          {:else if question_set}
            <!-- name deliberately empty: hides the component's details link
                 (the wizard manages the eval's details itself, and the name
                 isn't user-chosen yet at this step). -->
            <Questions
              name=""
              {spec_type}
              {property_values}
              {question_set}
              bind:selections
              bind:other_texts
              on_submit={on_continue_from_clarify}
              bind:error={questions_form_error}
              bind:submitting={questions_submitting}
              warn_before_unload={false}
              submit_label="Next"
            />
          {/if}
        {:else if current_step === "refine"}
          <!-- ── Step 3 — Refine ── -->
          {#if refined_preview_loading}
            <RefiningAnimation
              title="Refining Eval"
              description="Refining your eval with the feedback you provided."
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
            <!-- Both arms share the lean form: name + issue description.
                 Example fields are not part of the builder; real examples
                 come from the Step 4 generated data. -->
            <div class="mb-6">
              <FormElement
                label="Eval Name"
                description="A short name for your own reference (max 32 characters)."
                id="builder_eval_name"
                inputType="input"
                bind:value={name}
                validator={filename_string_short_validator}
              />
            </div>

            <div class="mb-4">
              <FormElement
                label="Issue Description"
                description="What the agent must avoid doing."
                id="builder_issue_description"
                inputType="textarea"
                height="large"
                bind:value={refined_property_values.issue_description}
              />
              {#if suggested_edits.issue_description?.reason_for_edit}
                <div class="text-xs text-gray-500 italic mt-2">
                  <span
                    class="tooltip tooltip-top before:z-50 before:whitespace-normal"
                    data-tip={suggested_edits.issue_description.reason_for_edit}
                  >
                    We updated this based on your answers.
                  </span>
                </div>
              {/if}
            </div>

            {#if refine_form_error}
              <!-- The Step 3 gate errors (e.g. a taken eval name). Without
                   this region the Next button silently does nothing. -->
              <div class="mt-4">
                <Warning
                  warning_color="error"
                  warning_message={refine_form_error.getMessage()}
                />
              </div>
            {/if}
            <div class="flex justify-end mt-8">
              <!-- The name gate runs the same validator the field shows, so
                   an invalid name cannot ride through generation and review
                   only to fail at save. -->
              <!-- FormContainer's compact submit spec, hand-rolled: this is a
                   bespoke form, but its action row should read the same as
                   the FormContainer-backed steps around it. -->
              <button
                class="relative btn btn-primary min-w-64 px-12"
                on:click={on_refine_submit}
                disabled={refine_submit_in_flight ||
                  filename_string_short_validator(name) !== null ||
                  !(refined_property_values.issue_description ?? "").trim()}
              >
                Next
                <span class="absolute opacity-80 right-4 text-xs font-light">
                  {#if isMacOS()}
                    <span class="tracking-widest">⌘↵</span>
                  {:else}
                    <span>ctrl ↵</span>
                  {/if}
                </span>
              </button>
            </div>
          {/if}
        {:else if current_step === "generate"}
          <!-- ── Step 4 — Generate ── -->
          {#if fallback_run_config_name}
            <Warning
              warning_color="primary"
              warning_icon="info"
              warning_message={`Using run config ${fallback_run_config_name}. Set a default in task settings to silence this notice.`}
            />
          {/if}
          {#if generation_loading && !pipeline_running}
            <!-- Plan, SU generation, and input minting are each one long
                 request/job (minutes at a 40-case batch) — the standard
                 animation warning line sets the expectation, matching every
                 other long wait in the app. Multi-turn is building
                 conversations, so it uses the chat-bubble animation;
                 single-turn keeps the analysis one. The minting stage adds
                 the house batch-progress readout — it completes one input
                 at a time, so real progress exists to show. -->
            {#if is_multi_turn}
              <ConversationAnimation
                title={generate_animation_title}
                description={generate_animation_description}
                warning={generate_animation_warning}
              />
            {:else}
              <AnalyzingAnimation
                title={generate_animation_title}
                description={generate_animation_description}
                warning={generate_animation_warning}
              />
              {#if generation_phase === "minting_inputs"}
                <div class="flex flex-col items-center mt-2">
                  <progress
                    class="progress w-56 progress-success"
                    value={minting_done}
                    max={minting_total}
                  ></progress>
                  <div class="font-light text-xs text-center mt-1">
                    {minting_done} of {minting_total} inputs written
                  </div>
                </div>
              {/if}
            {/if}
          {/if}
          {#if pipeline_running}
            <!-- The drive stage: the arm's animation plus the house
                 batch-progress readout (slim bar + tiny count line,
                 mirroring /generate's batch generation). Multi-turn's bar
                 tracks TURNS for smooth motion (cases complete in
                 concurrency waves), so its count line LEADS with turns;
                 single-turn cases are one run each, so its bar counts
                 finished cases directly. The title stays static: the live
                 counts belong to the readout under the bar. -->
            {#if is_multi_turn}
              <ConversationAnimation
                title="Creating Eval Data"
                description="Simulating conversations with your agent and judging each one."
                warning={null}
              />
              <div class="flex flex-col items-center mt-2">
                <progress
                  class="progress w-56 progress-success"
                  value={multi_turn_turns_done}
                  max={multi_turn_total_turns}
                ></progress>
                <!-- Turns, not cases: cases finish in concurrency waves, so
                     the turn count is the one that actually moves while the
                     batch runs. It's the only live count on this screen. -->
                <div class="font-light text-xs text-center mt-1">
                  {multi_turn_turns_done} of {multi_turn_total_turns} turns complete{#if pipeline_failed_count > 0},
                    {pipeline_failed_count} failed{/if}
                </div>
              </div>
            {:else}
              <AnalyzingAnimation
                title="Creating Eval Data"
                description="Running your task on each test input and judging the result."
                warning={null}
              />
              <div class="flex flex-col items-center mt-2">
                <progress
                  class="progress w-56 progress-success"
                  value={judged_case_count + pipeline_failed_count}
                  max={pipeline_total_cases}
                ></progress>
                <div class="font-light text-xs text-center mt-1">
                  {judged_case_count} of {pipeline_total_cases} judged{#if pipeline_failed_count > 0},
                    {pipeline_failed_count} failed{/if}
                </div>
              </div>
            {/if}
          {/if}
          {#if preparing_review}
            <!-- The claims gate: the progress screen holds while the
                 selected traces' claims build, so review opens fully
                 loaded — Previous can revisit any earlier trace, so every
                 selected claim set must be resolved up front. -->
            <svelte:component
              this={is_multi_turn ? ConversationAnimation : AnalyzingAnimation}
              title="Preparing Review"
              description={`Flagging possible mistakes in each ${judged_noun} for you to review.`}
              warning={null}
            />
            <div class="flex flex-col items-center mt-2">
              <progress
                class="progress w-56 progress-success"
                value={selected_claims_resolved}
                max={selected_trace_indices.length}
              ></progress>
              <div class="font-light text-xs text-center mt-1">
                Preparing review: {selected_claims_resolved} of {selected_trace_indices.length}
                ready
              </div>
            </div>
          {/if}
          <!-- The two failure surfaces are one chain so only ever one can
               render: the claims gate runs after a successful drive, so its
               error is the later, more specific one and takes priority. -->
          {#if claims_gate_error}
            <!-- Config-class build failure — same error+retry surface as
                 the wizard's other loading stages. -->
            <Warning
              warning_color="error"
              warning_message={claims_gate_error}
            />
            <div class="text-center py-4 flex justify-center gap-2">
              <button
                class="btn btn-outline"
                on:click={() => {
                  claims_gate_error = null
                }}
              >
                {is_multi_turn ? "Back to Scenarios" : "Back to Plan"}
              </button>
              <button
                class="btn btn-primary"
                on:click={() => start_claims_gate(true)}
              >
                Retry
              </button>
            </div>
          {:else if generation_error}
            <Warning warning_color="error" warning_message={generation_error} />
            <div class="text-center py-4 flex justify-center gap-2">
              {#if batch_plan !== null}
                <!-- Drive failed after approval — let the user rework the plan
                     instead of only retrying it verbatim. -->
                <button
                  class="btn btn-outline"
                  on:click={() => {
                    generation_error = null
                  }}
                >
                  {is_multi_turn ? "Back to Scenarios" : "Back to Plan"}
                </button>
              {/if}
              <button
                class="btn btn-primary"
                on:click={on_continue_from_generate_step}
              >
                Retry
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
                    case_noun,
                  )}
                />
              </div>
            {/if}
            <!-- Plan approval: the run starts only after the user approves
                 the plan — the shared /generate batch-plan surface,
                 relabelled per arm (scenarios / planned test inputs). The
                 primary button runs immediately with the default model
                 lanes; the settings link (slotted above the button) opens
                 the same settings dialog to pick them first. -->
            <KilnProBatchPlan
              plan={batch_plan}
              summary_out_of_sync={batch_plan_edited}
              header_label={is_multi_turn ? "Scenarios" : "Planned Test Inputs"}
              subheader={is_multi_turn
                ? "Each scenario becomes one eval input. Edit any before starting."
                : "Each plan line becomes one test input your task runs on. Edit any before starting."}
              regenerate_label={is_multi_turn ? "New Scenarios" : "New Plan"}
              on_generate_inputs={start_drive_with_defaults}
              on_regenerate={on_new_plan_with_confirm}
              on_delete_prompt={on_delete_plan_prompt}
              hide_generate_button={has_data_accepted}
              generate_button_outline={has_driven_results &&
                drive_stop !== null}
              generate_button_label={is_multi_turn
                ? `Create ${batch_plan.prompts.length} Eval Input${
                    batch_plan.prompts.length === 1 ? "" : "s"
                  }`
                : `Run Task on ${batch_plan.prompts.length} Input${
                    batch_plan.prompts.length === 1 ? "" : "s"
                  }`}
            >
              <svelte:fragment slot="advanced">
                {#if !has_data_accepted}
                  <!-- v1 wizard idiom for a secondary action by the primary
                       (see refine_spec's "or Save Refined Eval…" link). -->
                  <div class="flex flex-row gap-1 items-baseline">
                    <span class="text-sm text-gray-500">or</span>
                    <button
                      class="link underline text-sm text-gray-500"
                      on:click={open_drive_settings}
                    >
                      choose which models to use
                    </button>
                  </div>
                {/if}
              </svelte:fragment>
            </KilnProBatchPlan>
            <!-- Wizard chrome stays outside the shared component (it has no
                 slots): once this exact plan has driven results, offer the
                 way forward to review. Stepping back is the browser's Back. -->
            {#if has_driven_results}
              <!-- Conversations were already driven from this exact plan —
                   returning to the results doesn't re-spend model calls.
                   Also the survivors path from the stop banner. -->
              <div class="flex flex-row justify-end mt-4">
                <div class="flex flex-row items-center gap-3">
                  <span class="font-light text-xs text-gray-500">
                    {#if trace_claims.length < driven_plan_size}
                      {trace_claims.length} of {driven_plan_size} eval inputs created
                    {:else}
                      {trace_claims.length} eval inputs created
                    {/if}
                  </span>
                  <!-- The screen's single solid primary: the re-drive button
                       on the plan surface above demotes to outline whenever
                       this one co-renders (see generate_button_outline). -->
                  <button
                    class="relative btn btn-primary min-w-64 px-12"
                    on:click={on_continue_with_survivors}
                  >
                    Next
                    <span
                      class="absolute opacity-80 right-4 text-xs font-light"
                    >
                      {#if isMacOS()}
                        <span class="tracking-widest">⌘↵</span>
                      {:else}
                        <span>ctrl ↵</span>
                      {/if}
                    </span>
                  </button>
                </div>
              </div>
            {/if}
          {:else if !generation_loading && !generation_error && !preparing_review && !claims_gate_error}
            <div class="flex justify-end mt-8">
              {#if trace_claims.length > 0}
                <!-- Generation already ran (navigated back into this step) —
                     continue to the existing results instead of re-running,
                     matching the browser Forward path. -->
                <button
                  class="relative btn btn-primary min-w-64 px-12"
                  on:click={continue_to_review}
                >
                  Next
                  <span class="absolute opacity-80 right-4 text-xs font-light">
                    {#if isMacOS()}
                      <span class="tracking-widest">⌘↵</span>
                    {:else}
                      <span>ctrl ↵</span>
                    {/if}
                  </span>
                </button>
              {:else}
                <!-- No results (a Back aborted generation). This branch is
                     only reachable with no plan (a plan renders the
                     approval view above), so planning is the next action —
                     both arms are plan-first. -->
                <button
                  class="relative btn btn-primary min-w-64 px-12"
                  on:click={on_plan_batch}
                >
                  {is_multi_turn ? "Draft Scenarios" : "Plan Test Inputs"}
                  <span class="absolute opacity-80 right-4 text-xs font-light">
                    {#if isMacOS()}
                      <span class="tracking-widest">⌘↵</span>
                    {:else}
                      <span>ctrl ↵</span>
                    {/if}
                  </span>
                </button>
              {/if}
            </div>
          {/if}
        {:else if current_step === "review"}
          <!-- ── Step 5 — Claim/Evidence review (trace hidden in a modal) ── -->
          {#if review_results_stale}
            <!-- The staleness gate, FIRST so no review or calibration screen
                 can render over results whose spec text changed. Blocking,
                 never destroying: reverting the description restores the
                 review exactly; only the explicit action discards. Derived
                 state, so this also covers browser Forward straight into
                 the review step. -->
            <Warning
              warning_color="warning"
              warning_message="Your eval's description changed since this eval data was created and reviewed. The judge was built from the previous description, so the results below no longer match. Revert the description (Back) to continue reviewing, or discard the results and create your eval data again."
            />
            <div class="flex justify-center gap-2 py-4">
              <button class="btn btn-outline" on:click={() => history.back()}>
                Back
              </button>
              <button class="btn btn-primary" on:click={discard_stale_results}>
                Discard Results &amp; Create Again
              </button>
            </div>
          {:else if calibration_phase === "refining"}
            <!-- The refine, as a visible stage the reviewer can watch and
                 abort rather than something that happens at save. -->
            <RefiningAnimation
              title="Improving Your Judge"
              description="Applying your feedback to improve the judge that grades your eval."
            />
          {:else if calibration_phase === "rejudging"}
            <!-- The pipeline progress surface in judge-only form: no drive,
                 no turns — one result per item as the stream lands. Static
                 title; the live count is the readout under the bar. -->
            <svelte:component
              this={is_multi_turn ? ConversationAnimation : AnalyzingAnimation}
              title="Re-checking Eval Data"
              description="Re-checking your eval data with the improved judge."
              warning={null}
            />
            <div class="flex flex-col items-center mt-2">
              <progress
                class="progress w-56 progress-success"
                value={rejudged_done + rejudge_failed_live}
                max={rejudge_total}
              ></progress>
              <div class="font-light text-xs text-center mt-1">
                {rejudged_done} of {rejudge_total} re-checked{#if rejudge_failed_live > 0},
                  {rejudge_failed_live} failed{/if}
              </div>
            </div>
          {:else if calibration_phase === "building_claims"}
            <!-- Same wait-for-all claims gate as the first round, held on the
                 review step: the re-review opens fully loaded. -->
            <svelte:component
              this={is_multi_turn ? ConversationAnimation : AnalyzingAnimation}
              title="Preparing Review"
              description={`Flagging possible mistakes in each ${judged_noun} for you to review.`}
              warning={null}
            />
            <div class="flex flex-col items-center mt-2">
              <progress
                class="progress w-56 progress-success"
                value={selected_claims_resolved}
                max={selected_trace_indices.length}
              ></progress>
              <div class="font-light text-xs text-center mt-1">
                Preparing review: {selected_claims_resolved} of {selected_trace_indices.length}
                ready
              </div>
            </div>
          {:else if calibration_error}
            <!-- Retryable re-judge failure — the grades that fed the refine
                 are intact, so Retry resumes at the re-check without paying
                 the refine again. The appended sentence names the other exit:
                 a failure that repeats every round (a case the re-check can
                 never complete) would otherwise leave Retry as the only
                 visible move. -->
            <Warning
              warning_color="error"
              warning_message={`${calibration_error.trimEnd().replace(/\.$/, "")}. You can also go back to review and save without refining further.`}
            />
            <div class="text-center py-4 flex justify-center gap-2">
              <button
                class="btn btn-outline"
                on:click={() => {
                  calibration_error = null
                }}
              >
                Back to Review
              </button>
              <button
                class="btn btn-primary"
                on:click={() => void run_calibration_round(true)}
              >
                Retry
              </button>
            </div>
          {:else if trace_claims.length === 0}
            <!-- Browser Forward can land here after results were cleared
                 (plan regenerated / drive restarted). Browser Back returns to
                 generation rather than showing an empty review. -->
            <Warning
              warning_color="warning"
              warning_message="There is nothing to review yet. Create your eval data first."
            />
          {:else}
            {#if calibration_rounds_completed > 0 && rejudge_shortfall_notice(calibration_failed_count, case_noun)}
              <!-- Cases without a fresh verdict sat the round out — say so
                   instead of letting the smaller subset pass unremarked. -->
              <div class="mb-4">
                <Warning
                  warning_color="primary"
                  warning_icon="info"
                  warning_message={rejudge_shortfall_notice(
                    calibration_failed_count,
                    case_noun,
                  )}
                />
              </div>
            {/if}
            <!-- Keyed per round: a new round replaces the subset and resets
                 every grade, so the review component restarts on the new
                 selection instead of pointing at a stale index. -->
            {#key calibration_rounds_completed}
              <!-- is_multi_turn is the task-level half of the review-shape
                   gate: a single-turn task reviews its short traces on the
                   trace itself rather than on the claims distilled from it. -->
              <ClaimEvidenceReview
                traces={trace_claims}
                bind:verdicts={trace_reviews}
                selected_indices={selected_trace_indices}
                {judged_noun}
                {is_multi_turn}
                {on_open_trace}
                on_save={on_advance_to_save}
                save_disabled={!save_gate_met}
                save_label={review_cta_state === "refine"
                  ? "Refine Judge"
                  : "Save"}
                save_tooltip={review_cta_state === "refine"
                  ? refine_judge_tooltip(review_disagreement_count, judged_noun)
                  : null}
                bind:on_last_trace={review_on_last_trace}
              />
            {/key}
            {#if calibration_refine_error}
              <!-- A failed refine attempt, reported inline under the review
                   actions. Rendered independently of the opt-out link below:
                   editing grades can drop the save gate (a fresh disagreement
                   without a reason yet), and the failure must not vanish
                   while the user is reacting to it. -->
              <div class="text-sm text-center text-error mt-2">
                {calibration_refine_error}
              </div>
            {/if}
            {#if review_cta_state === "refine" && save_gate_met && review_on_last_trace}
              <!-- The loop's opt-out, in the wizard's quiet-link idiom (the
                   data-guide refine flow): saves immediately with the judge
                   the reviewer graded — no dialog. Only offered where the
                   primary CTA itself renders — a refine on the last trace —
                   so it never sits under a Next button, where one unconfirmed
                   click would save mid-review. -->
              <div class="flex flex-col items-end mt-2">
                <button
                  type="button"
                  class="link underline text-sm text-gray-500"
                  on:click={save_without_refining}
                >
                  Save Without Refining Further
                </button>
              </div>
            {/if}
          {/if}
        {:else if current_step === "save"}
          <!-- ── Save (transition out of Step 5) ── -->
          {#if saving}
            <SavingAnimation
              title="Creating Eval"
              description={save_animation_description}
            />
          {:else if save_error}
            <Warning warning_color="error" warning_message={save_error} />
            <div class="text-center py-4">
              <button class="btn btn-primary" on:click={on_save}>Retry</button>
            </div>
          {/if}
        {:else if current_step === "done"}
          <!-- Fallback: save succeeded but no eval_id/spec_id to redirect to.
               Centered completion card, same idiom as the git-import done
               screen. -->
          <div class="flex flex-col items-center py-8 gap-4">
            <div class="text-success">
              <svg
                class="w-16 h-16"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M16 9L10 15.5L7.5 13M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21Z"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </div>
            <h2 class="text-xl font-medium">Eval Created</h2>
            <p class="text-sm text-gray-500 text-center max-w-md">
              Your eval is ready to run.
            </p>
            <div class="flex flex-row gap-4 mt-4">
              <button class="btn btn-primary btn-wide" on:click={back_to_task}>
                Back to Evals
              </button>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </AppPage>
</div>

<!-- Drive settings dialog (SDG's Generation Settings pattern): the primary
     button runs immediately with the default lanes, so this opens only from
     the settings link (pre-run model choice) or as fail-loud recovery when
     a default lane can't be resolved. Its submit starts the run either way.
     Model-only lanes — the user-simulator, input generator, and judge are
     fixed-prompt internal roles, so no run-config extras. Lane filters: the
     simulator and input generator want a data-gen model (SDG's settings);
     judge needs structured output (v1 judge form's settings). With no
     usable model, the dropdowns' own empty state links to provider settings
     (same-tab, so the models list is fresh when the user returns) and
     submit refuses to start. -->
<Dialog bind:this={drive_settings_dialog} title="Advanced Settings">
  <FormContainer
    submit_label={is_multi_turn
      ? `Create ${planned_total} Eval Input${planned_total === 1 ? "" : "s"}`
      : `Run Task on ${planned_total} Input${planned_total === 1 ? "" : "s"}`}
    bind:submitting={drive_settings_submitting}
    error={drive_settings_error}
    on:submit={submit_drive_settings}
    keyboard_submit={false}
  >
    {#if is_multi_turn}
      <AvailableModelsDropdown
        label="Model that plays the user"
        description="Plays your agent's user in each test conversation."
        bind:model={su_model_combined}
        bind:model_name={su_model_id}
        bind:provider_name={su_provider_id}
        settings={{
          requires_data_gen: true,
          suggested_mode: "data_gen",
        }}
      />
    {:else}
      <AvailableModelsDropdown
        label="Model that writes the test inputs"
        description="Writes one test input from each approved plan line; your task then runs on them."
        bind:model={input_gen_model_combined}
        bind:model_name={input_gen_model_id}
        bind:provider_name={input_gen_provider_id}
        settings={{
          requires_data_gen: true,
          suggested_mode: "data_gen",
        }}
      />
    {/if}
    <AvailableModelsDropdown
      label="Model that judges the results"
      description={`Reviews each ${judged_noun} against your eval's criteria and decides pass or fail.`}
      bind:model={judge_model_combined}
      bind:model_name={judge_model_id}
      bind:provider_name={judge_provider_id}
      settings={{
        requires_structured_output: true,
        suggested_mode: "evals",
      }}
    />
  </FormContainer>
</Dialog>

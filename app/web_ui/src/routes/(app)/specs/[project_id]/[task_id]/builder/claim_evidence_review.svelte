<script lang="ts">
  // Claim review step — one trace at a time. The reviewer reads the Overview,
  // then votes Agree or Disagree on every claim the builder wrote, opening a
  // [n] citation into the trace modal only for the hard calls. Everything on
  // screen is the builder's text: the judge's score and reasoning never
  // render here, since the reviewer's calls are what calibrate the judge.
  //
  // The overall pass/fail call is derived from the verdict claim's grade when
  // the builder wrote one (it is always the last claim). When the builder
  // omitted it, a Pass/Fail row after the claims asks the call outright. Continue
  // is gated on the whole trace being graded (is_trace_reviewed).
  //
  // Subset review: `selected_indices` is the judge-stratified sample the
  // reviewer grades (sized to the golden answer key) — the review shows
  // exactly these traces, mirroring the single-turn flow where the user
  // reviews exactly what's presented. Claims build lazily: opening a trace
  // triggers its build via `on_open_trace`, and the panel shows a building or
  // error state until they arrive. A failed build still lets the reviewer
  // answer the overall call from the transcript, so the trace counts toward
  // the save gate without a rebuild.
  import ClaimCard from "./claim_card.svelte"
  import ClaimText from "./claim_text.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  // The nav row hand-rolls FormContainer's submit button, so it renders the
  // same keyboard hint using the same platform check.
  import { isMacOS } from "$lib/utils/platform"
  import {
    has_verdict_claim,
    is_trace_reviewed,
    type Citation,
    type JudgeScore,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"

  export let traces: TraceClaims[]
  // Two-way bound so the parent reads verdicts at save time.
  export let verdicts: TraceReview[]
  // Indices of the traces the reviewer grades; empty = all.
  export let selected_indices: number[] = []
  // Called with the trace index being shown — the parent builds its claims
  // if needed. Also the retry hook for a failed build.
  export let on_open_trace: (index: number) => void = () => {}
  export let on_save: () => void = () => {}
  // The review gate, computed by the parent (enough traces reviewed). Drives
  // the Save button's VISIBILITY (not just its enabled state): Save is hidden
  // until the gate is met, then takes the Continue slot on the last conversation.
  export let save_disabled = true
  // The primary action's label and optional tooltip, parent-owned so the
  // button can say what the click actually does (a review with disagreements
  // enters a judge-refine round instead of saving).
  export let save_label = "Save"
  export let save_tooltip: string | null = null
  // What the judge judged, in the caller's vocabulary: "conversation" for
  // multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // True while the reviewer is on the last selected trace — the only position
  // where the primary action renders. Bound out (read-only for the parent) so
  // anything the parent stacks under that action appears only alongside it.
  export let on_last_trace = false

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null

  // Names the judge, because the step header does. Claims are the decisions
  // the judge made, the verdict claim included, and the second sentence names
  // the one control every card carries.
  $: claims_description = `The decisions the judge made about this ${judged_noun}. Agree or disagree with each.`

  // Why the primary action is held disabled on the last trace. Stated in the
  // component's own terms (the parent owns how many grades the gate wants,
  // but every unmet case comes down to grading that isn't finished).
  const SAVE_GATE_TOOLTIP =
    "Finish grading to continue. Disagreements need a reason."

  $: selected =
    selected_indices.length > 0 ? selected_indices : traces.map((_, i) => i)
  $: current = traces[current_index]
  $: current_verdicts = verdicts[current_index]

  // Start on the first selected trace (a fresh mount has current_index 0,
  // which may be unselected under subset review).
  let started_on_selected = false
  $: if (!started_on_selected && selected.length > 0) {
    started_on_selected = true
    current_index = selected[0]
  }

  // Report every shown trace to the parent so lazily-built claims kick off
  // the moment the reviewer lands on a trace (idempotent parent-side).
  $: report_opened(current_index)
  function report_opened(index: number) {
    if (traces[index]) on_open_trace(index)
  }

  // Keep original indices, since verdicts are positional.
  $: visible = (current?.claims ?? []).map((claim, index) => ({ claim, index }))

  // The overall call is asked outright only when nothing on screen records
  // it: the builder omitted the verdict claim, or the build failed and there
  // are no claims at all. Never while the claims are still on their way.
  $: asks_overall =
    !!current &&
    (current.claims_state === "error" ||
      (current.claims_state === "built" && !has_verdict_claim(current)))

  function open_citation(citation: Citation) {
    if (current) trace_modal?.open_citation(current, citation)
  }

  function set_overall(value: JudgeScore) {
    // Assigned through `verdicts` so the change reaches the parent's binding.
    if (verdicts[current_index]) verdicts[current_index].overall = value
  }

  // Prev/Continue walk the selected sequence.
  function go_prev() {
    const prior = selected.filter((i) => i < current_index)
    if (prior.length > 0) current_index = prior[prior.length - 1]
  }
  function go_next() {
    const later = selected.filter((i) => i > current_index)
    if (later.length > 0) current_index = later[0]
  }
  $: has_prev = selected.some((i) => i < current_index)
  $: has_next = selected.some((i) => i > current_index)
  $: on_last_trace = !has_next

  // Continue is gated on the CURRENT conversation being fully answered. Save
  // takes the Continue slot on the last conversation, but only once the overall
  // gate is met.
  $: current_reviewed = is_trace_reviewed(current, current_verdicts)
</script>

<div>
  {#if current && current_verdicts}
    {#if current.overview}
      <!-- The Overview, with the trace escape hatch beside it. The reviewer is
           expected to read this, which is what lets the claims below stay
           short. Its [n] chips open the same trace view the claim cards do. -->
      <div
        id="review-overview"
        class="rounded-lg border bg-base-200/40 p-4 mb-4"
      >
        <div class="flex items-start justify-between gap-3">
          <span class="text-sm font-medium">Overview</span>
          <button
            id="view-full-trace"
            class="btn btn-xs btn-ghost flex-none"
            on:click={() => current && trace_modal?.open_trace(current)}
          >
            View Full Trace
          </button>
        </div>
        <p class="text-sm text-gray-600 mt-2 leading-relaxed">
          <ClaimText
            text={current.overview.text}
            citations={current.overview.citations}
            on_cite={open_citation}
          />
        </p>
      </div>
    {:else}
      <!-- Nothing built yet (or the build failed), so the escape hatch stands
           alone: the trace is all there is to read. -->
      <div class="flex items-center justify-end mb-4">
        <button
          id="view-full-trace"
          class="btn btn-xs btn-ghost"
          on:click={() => current && trace_modal?.open_trace(current)}
        >
          View Full Trace
        </button>
      </div>
    {/if}

    {#if current.claims_state === "built"}
      <div class="space-y-3">
        <div class="flex flex-col gap-1">
          <span class="text-sm font-medium">Claims</span>
          <div class="text-sm text-gray-500">{claims_description}</div>
        </div>
        {#each visible as { claim, index } (index)}
          <ClaimCard
            {claim}
            {index}
            bind:verdict={current_verdicts.claim_verdicts[index]}
            on_cite={open_citation}
          />
        {/each}
      </div>
    {:else if current.claims_state === "error"}
      <Warning
        warning_color="error"
        warning_message={`Couldn't analyze this ${judged_noun}: ${
          current.claims_error ?? "unknown error"
        }`}
      />
    {:else}
      <!-- "unbuilt" | "building" — the build starts on open, so both render
           as in-progress. -->
      <div class="text-center py-12 text-gray-500">
        <div class="loading loading-dots loading-md mb-2"></div>
        <div class="text-sm">Analyzing this {judged_noun}…</div>
      </div>
    {/if}

    {#if asks_overall}
      <!-- The overall call, asked outright and last: no claim on screen
           records pass or fail, so the reviewer answers it here, from the
           claims above or from the transcript when there are none. Pass/Fail
           is the pair the spec builder's review table answers this question
           with. -->
      <div
        id="review-overall"
        class="card card-bordered shadow-md p-4 bg-base-100 border-base-300 mt-3"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="font-medium text-sm">Does this {judged_noun} pass?</div>
          <div class="flex gap-2 flex-none">
            <button
              id="overall-pass"
              class="btn btn-sm {current_verdicts.overall === 'pass'
                ? 'btn-success'
                : 'btn-outline'}"
              on:click={() => set_overall("pass")}
            >
              Pass
            </button>
            <button
              id="overall-fail"
              class="btn btn-sm {current_verdicts.overall === 'fail'
                ? 'btn-error'
                : 'btn-outline'}"
              on:click={() => set_overall("fail")}
            >
              Fail
            </button>
          </div>
        </div>
      </div>
    {/if}

    {#if current.claims_state === "error"}
      <div class="text-center py-4">
        <!-- Outline primary: recovering a failed analysis is the obvious next
             action, but the review's own forward button is on the same
             screen, and only one solid primary belongs there. -->
        <button
          class="btn btn-outline btn-primary"
          on:click={() => on_open_trace(current_index)}
        >
          Retry Analysis
        </button>
      </div>
    {/if}
  {/if}

  <!-- Bottom nav: the review-order count inline beside a right-aligned
       [Previous][Continue] cluster. Wizard-step navigation is the browser's
       Back/Forward. Previous walks back whenever there's an earlier trace;
       Continue is gated on finishing the current one. On the last conversation
       the Continue slot becomes the primary action. -->
  <div class="flex flex-col items-end gap-1 mt-8">
    <div class="flex items-center gap-2">
      <!-- Count inline beside the controls — the run-control pattern
           (see docs/extractors' "Completed N of M"). -->
      <span class="text-xs font-light text-gray-500 mr-2">
        {selected.indexOf(current_index) + 1} of {selected.length}
      </span>
      <button
        class="btn btn-sm btn-outline"
        on:click={go_prev}
        disabled={!has_prev}>Previous</button
      >
      <!-- Continue carries the wide primary spec (Previous stays small): it is the
           forward action on every trace but the last, where the same slot
           becomes the save. The ⌘↵ hint rides only the enabled save variant —
           the wizard's shortcut fires the save action, and only once the gate
           is met. -->
      {#if has_next}
        <button
          class="btn btn-primary min-w-64 px-12"
          on:click={go_next}
          disabled={!current_reviewed}>Continue</button
        >
      {:else if !save_disabled}
        <!-- Last conversation, gate met: the primary action replaces Continue.
             The label is parent-owned (Save vs Refine Judge) so it never
             promises a save that a calibration round would intercept. -->
        {#if save_tooltip}
          <div class="tooltip tooltip-left" data-tip={save_tooltip}>
            <button
              class="relative btn btn-primary min-w-64 px-12"
              on:click={on_save}
            >
              {save_label}
              <span class="absolute opacity-80 right-4 text-xs font-light">
                {#if isMacOS()}
                  <span class="tracking-widest">⌘↵</span>
                {:else}
                  <span>ctrl ↵</span>
                {/if}
              </span>
            </button>
          </div>
        {:else}
          <button
            class="relative btn btn-primary min-w-64 px-12"
            on:click={on_save}
          >
            {save_label}
            <span class="absolute opacity-80 right-4 text-xs font-light">
              {#if isMacOS()}
                <span class="tracking-widest">⌘↵</span>
              {:else}
                <span>ctrl ↵</span>
              {/if}
            </span>
          </button>
        {/if}
      {:else}
        <!-- Last conversation, gate not met: the same primary action, held
             disabled with the reason on hover. A "Continue" here would point at
             nothing, so the slot stays the save action throughout. No ⌘↵
             hint: the shortcut is gated on the same rule as this button. -->
        <div class="tooltip tooltip-left" data-tip={SAVE_GATE_TOOLTIP}>
          <button class="btn btn-primary min-w-64 px-12" disabled>
            {save_label}
          </button>
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- One trace rendering for both arms: a single-turn run is a conversation of
     one turn, so the modal no longer needs to be told which arm it is on. -->
<ClaimTraceModal bind:this={trace_modal} />

<script lang="ts">
  // Claim/Evidence review step — one trace at a time. The reviewer grades a
  // few statements (Correct/Incorrect on distilled claims) without reading
  // the trace, opening a [n] citation into the trace modal only for the
  // hard calls. Claim text never states the verdict — the reviewer's calls
  // calibrate the judge, so its label must not anchor them; the overall
  // verdict lives on the final card, pinned last as the conclusion.
  //
  // Subset review: `selected_indices` is the judge-stratified sample the
  // reviewer grades (sized to the golden answer key) — the review shows
  // exactly these traces, mirroring the single-turn flow where the user
  // reviews exactly what's presented. Claims build lazily (multi-turn):
  // opening a trace triggers its build via `on_open_trace`, and the panel
  // shows a building/error state until they arrive.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  // The nav row hand-rolls FormContainer's submit button, so it renders the
  // same keyboard hint using the same platform check.
  import { isMacOS } from "$lib/utils/platform"
  import {
    blind_final_judgement,
    is_trace_reviewed,
    type Citation,
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
  // until the gate is met, then takes the Next slot on the last conversation.
  export let save_disabled = true
  // The primary action's label and optional tooltip, parent-owned so the
  // button can say what the click actually does (a review with disagreements
  // enters a judge-refine round instead of saving).
  export let save_label = "Save"
  export let save_tooltip: string | null = null
  // What the judge judged, for the verdict card's headline: "conversation"
  // for multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // True while the reviewer is on the last selected trace — the only position
  // where the primary action renders. Bound out (read-only for the parent) so
  // anything the parent stacks under that action appears only alongside it.
  export let on_last_trace = false

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null

  // The server returns every claim importance-ordered; we show only the most
  // important few plus the (always-present, top-level) final judgement pinned
  // last as the conclusion. Claims may be EMPTY for trivial evals — the final
  // judgement alone is then the whole review.
  const MAX_CLAIMS = 3

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
  $: visible = (current?.claims ?? [])
    .map((claim, index) => ({ claim, index }))
    .slice(0, MAX_CLAIMS - 1)

  function open_citation(citation: Citation) {
    if (current) trace_modal?.open_citation(current, citation)
  }

  // Prev/Next walk the selected sequence.
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

  // Next is gated on the CURRENT conversation being fully answered — the same
  // per-trace completeness the old progress dots colored. Save takes the Next
  // slot on the last conversation, but only once the overall gate is met.
  $: current_reviewed = is_trace_reviewed(current, current_verdicts)
</script>

<div>
  {#if current && current_verdicts}
    <!-- Trace header: just the quiet escape hatch to the full trace. The
         verdict label stays off this row — the overall card carries it,
         pinned last — and review-order position now lives under the nav. -->
    <div class="flex items-center justify-end mb-4">
      <button
        class="btn btn-xs btn-ghost"
        on:click={() => current && trace_modal?.open_trace(current)}
      >
        View Full Trace
      </button>
    </div>

    {#if current.claims_state === "built"}
      <div class="space-y-3">
        {#each visible as { claim, index } (index)}
          <ClaimCard
            {claim}
            bind:verdict={current_verdicts.claim_verdicts[index]}
            on_cite={open_citation}
          />
        {/each}
        <!-- The overall verdict, pinned last as the conclusion. Always present
             even when the claims list is empty. -->
        {#if current.final_judgement}
          <ClaimCard
            claim={current.final_judgement}
            bind:verdict={current_verdicts.final_judgement_verdict}
            on_cite={open_citation}
            on_view_trace={() => current && trace_modal?.open_trace(current)}
            is_final_judgement
            {judged_noun}
          />
        {/if}
      </div>
    {:else if current.claims_state === "error"}
      <Warning
        warning_color="error"
        warning_message={`Couldn't analyze this ${judged_noun}: ${
          current.claims_error ?? "unknown error"
        }`}
      />
      <!-- The claims failed, but the overall pass/fail call is still
           answerable from the transcript — render the blind verdict card so
           the reviewer can grade it (and reach the save gate) without a
           paid re-drive. "View Full Trace" above opens the transcript. -->
      <div class="space-y-3 mt-3">
        <ClaimCard
          claim={blind_final_judgement(current)}
          bind:verdict={current_verdicts.final_judgement_verdict}
          is_final_judgement
          {judged_noun}
        />
      </div>
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
    {:else}
      <!-- "unbuilt" | "building" — the build starts on open, so both render
           as in-progress. -->
      <div class="text-center py-12 text-gray-500">
        <div class="loading loading-dots loading-md mb-2"></div>
        <div class="text-sm">Analyzing this {judged_noun}…</div>
      </div>
    {/if}
  {/if}

  <!-- Bottom nav: the review-order count inline beside a right-aligned
       [Previous][Next] cluster. Wizard-step navigation is the browser's
       Back/Forward. Previous walks back whenever there's an earlier trace;
       Next is gated on finishing the current one. On the last conversation
       the Next slot becomes the primary action. -->
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
      <!-- Next is pagination, not the step's forward action: it's the small
           twin of Previous, and the wide submit spec below belongs only to
           the primary action on the last trace. The ⌘↵ hint likewise rides
           only the enabled save variant — the wizard's shortcut fires the
           save action, and only once the gate is met. -->
      {#if has_next}
        <button
          class="btn btn-primary min-w-64 px-12"
          on:click={go_next}
          disabled={!current_reviewed}>Next</button
        >
      {:else if !save_disabled}
        <!-- Last conversation, gate met: the primary action replaces Next.
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
             disabled with the reason on hover. A "Next" here would point at
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

<ClaimTraceModal bind:this={trace_modal} />

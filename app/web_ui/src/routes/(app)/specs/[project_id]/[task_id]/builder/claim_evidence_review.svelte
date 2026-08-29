<script lang="ts">
  // Claim/Evidence review step — one trace at a time. The reviewer answers the
  // overall pass/fail call without reading the trace, opening a [n] citation
  // into the trace modal only for the hard calls. Nothing on screen states the
  // call before that answer — the reviewer's calls calibrate the judge, so its
  // label must not anchor them.
  //
  // The overall call is the only answer the gate requires (is_trace_reviewed
  // wants it plus a reason for any dissent), so its card comes FIRST and the
  // distilled claims sit under it behind a Claims disclosure, collapsed.
  // Claim grades were always optional, so folding them changes no behavior.
  //
  // Subset review: `selected_indices` is the judge-stratified sample the
  // reviewer grades (sized to the golden answer key) — the review shows
  // exactly these traces, mirroring the single-turn flow where the user
  // reviews exactly what's presented. Claims build lazily (multi-turn):
  // opening a trace triggers its build via `on_open_trace`, and the panel
  // shows a building/error state until they arrive.
  //
  // single-turn output is cheaper to read whole than as claims, so that trace
  // renders inline and the reviewer labels the output blind, with the claims
  // one click behind [View Claims]. Everything else keeps the claim stack with
  // the trace behind [View Full Trace]. Both write the same verdicts, so save,
  // gate and refine see one shape.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  // The single-turn review anatomy (Input field + Output section), shared with
  // the trace modal so the trace reads the same inline and behind the button.
  // The nav row hand-rolls FormContainer's submit button, so it renders the
  // same keyboard hint using the same platform check.
  import { isMacOS } from "$lib/utils/platform"
  import {
    blind_final_judgement,
    final_judgement_reason,
    is_trace_reviewed,
    type Citation,
    type Claim,
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
  // The task-level half of the review-shape gate (the other half is the
  // trace's own output length). The default describes a single-turn task,
  // matching judged_noun's default.
  export let is_multi_turn = false
  // True while the reviewer is on the last selected trace — the only position
  // where the primary action renders. Bound out (read-only for the parent) so
  // anything the parent stacks under that action appears only alongside it.
  export let on_last_trace = false

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null
  // The server returns every claim importance-ordered, so the first few are
  // the ones worth reading; the review shows that many and no more. The "- 1"
  // is a historical shape, not a reserved slot: the final judgement used to be
  // the third card in this stack and now leads the review as its own card, so
  // the effective cap here is simply two claims. Real traces carry more than
  // that, which is why the disclosure names the claims without counting them.
  // Claims may also be EMPTY for trivial evals — the
  // final judgement alone is then the whole review.
  const MAX_CLAIMS = 3

  // The claims disclosure, in the batch plan's row idiom
  // (kiln_pro_prompts_table) so the two surfaces read as one app. Folded again
  // on every move: the card asks its question blind, and carrying the previous
  // example's expansion forward would answer part of the next one before it is
  // asked. Opening it is a choice about the example in front of the reviewer,
  // not a standing preference.
  let claims_expanded = false
  // "The main facts" rather than "the facts": the cards below are the top of
  // an importance-ordered list, not all of it. Second sentence names the only
  // control the claim cards carry, so the description can never describe an
  // answer the reviewer is not offered.
  // Names the judge, because the rest of this step does: the header says a
  // judge scored the runs, and the feedback box below is labelled Teach the
  // Judge. "Score" is the house verb for what it did.
  $: claims_disclosure_description = `The main facts the judge used to score this ${judged_noun}. Disagree with any that are wrong.`
  $: claims_toggle_label = `${claims_expanded ? "Hide" : "Show"} claims`

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

  // The judgement the blind card grades. The distilled final judgement
  // whenever the claims build produced one carrying a real reason; otherwise
  // the judge's own reasoning, which is all a reason-less build leaves to
  // read. Both pin expected_result to the judge's score, which is what the
  // card computes agreement against.
  $: blind_judgement = current ? blind_judgement_for(current) : null
  function blind_judgement_for(t: TraceClaims): Claim {
    const judgement = t.final_judgement
    return judgement && final_judgement_reason(judgement.claim)
      ? judgement
      : blind_final_judgement(t)
  }

  // Prev/Next walk the selected sequence. Both fold the claims: the next
  // example is asked from scratch.
  function go_prev() {
    const prior = selected.filter((i) => i < current_index)
    if (prior.length > 0) current_index = prior[prior.length - 1]
    claims_expanded = false
  }
  function go_next() {
    const later = selected.filter((i) => i > current_index)
    if (later.length > 0) current_index = later[0]
    claims_expanded = false
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
    <!-- Trace header: the quiet escape hatch to the trace the review demotes.
         The verdict label stays off this row (nothing states the call before
         the reviewer answers) and review-order position lives under the nav. -->
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
        <!-- The overall call, FIRST and asked blind: it is the only answer the
             gate requires, and the trace is behind a button, so the card
             carries the judgement's reason and its cited evidence to answer
             from. Always present even when the claims list is empty. -->
        {#if blind_judgement}
          <ClaimCard
            claim={blind_judgement}
            bind:verdict={current_verdicts.final_judgement_verdict}
            on_cite={open_citation}
            on_view_trace={() => current && trace_modal?.open_trace(current)}
            is_final_judgement
            blind
            {judged_noun}
          />
        {/if}
        {#if visible.length > 0}
          <!-- The claims, folded. Optional to grade, so they read as backing
               material for the call above rather than as the review itself. -->
          <div class="rounded-lg border">
            <button
              class="w-full flex items-center justify-between px-4 py-3 text-left"
              aria-label={claims_toggle_label}
              aria-expanded={claims_expanded}
              on:click={() => (claims_expanded = !claims_expanded)}
            >
              <div class="flex flex-col gap-2">
                <!-- No count. The list is capped to the most important few,
                     so any number here invites "of how many?" and the honest
                     answer is a remainder the reviewer cannot reach. The row
                     names what is behind it and nothing more. -->
                <span class="text-sm font-medium">Claims</span>
                {#if claims_expanded}
                  <div class="text-sm text-gray-500">
                    {claims_disclosure_description}
                  </div>
                {/if}
              </div>
              <div class="flex items-center text-sm text-gray-500">
                <svg
                  class="w-4 h-4 transition-transform {claims_expanded
                    ? 'rotate-180'
                    : ''}"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </button>
            {#if claims_expanded}
              <div class="space-y-3 p-4 pt-0">
                {#each visible as { claim, index } (index)}
                  <ClaimCard
                    {claim}
                    bind:verdict={current_verdicts.claim_verdicts[index]}
                    on_cite={open_citation}
                  />
                {/each}
              </div>
            {/if}
          </div>
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
      <!-- Next carries the wide primary spec (Previous stays small): it is the
           forward action on every trace but the last, where the same slot
           becomes the save. The ⌘↵ hint rides only the enabled save variant —
           the wizard's shortcut fires the save action, and only once the gate
           is met. -->
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

<!-- The modal renders the arm this review is on: single-turn gets the same two
     sections as the inline surface, multi-turn the chat transcript. The arm is
     passed rather than inferred, because this component is the one that knows
     it — a single-turn trace can look like a conversation and vice versa. -->
<ClaimTraceModal bind:this={trace_modal} single_turn={!is_multi_turn} />

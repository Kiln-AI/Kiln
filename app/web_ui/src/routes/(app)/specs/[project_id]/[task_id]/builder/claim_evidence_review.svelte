<script lang="ts">
  // Claim/Evidence review step — one trace at a time. The reviewer answers a
  // few questions (agree/disagree on distilled claims) without reading the
  // trace, opening a [n] citation into the trace modal only for the hard calls.
  //
  // Subset review: `selected_indices` is the judge-stratified default set the
  // reviewer is asked to grade (the golden answer key's size); the remaining
  // traces sit collapsed below — visible and ratable, just not required.
  // Claims build lazily (multi-turn): opening a trace triggers its build via
  // `on_open_trace`, and the panel shows a building/error state until then.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import {
    is_trace_reviewed,
    reviewed_trace_count,
    type Citation,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"

  export let traces: TraceClaims[]
  // Two-way bound so the parent reads verdicts at save time.
  export let verdicts: TraceReview[]
  // Indices of the traces the reviewer is asked to grade; empty = all.
  export let selected_indices: number[] = []
  // How many reviewed traces the save gate requires (drives the header count).
  export let review_target_count = 0
  // Called with the trace index being shown — the parent builds its claims
  // if needed. Also the retry hook for a failed build.
  export let on_open_trace: (index: number) => void = () => {}
  export let on_back: () => void = () => {}
  export let on_save: () => void = () => {}
  export let save_disabled = true
  export let save_disabled_tooltip: string | null = null

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null

  // The server returns every claim importance-ordered; we show only the most
  // important few plus the (always-present, top-level) final judgement pinned
  // last as the conclusion. Claims may be EMPTY for trivial evals — the final
  // judgement alone is then the whole review.
  const MAX_CLAIMS = 3

  $: selected =
    selected_indices.length > 0 ? selected_indices : traces.map((_, i) => i)
  $: unselected = traces.map((_, i) => i).filter((i) => !selected.includes(i))
  $: current = traces[current_index]
  $: current_verdicts = verdicts[current_index]
  $: reviewed_count = reviewed_trace_count(traces, verdicts)

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

  // Prev/Next walk the SELECTED sequence; from an unselected trace they jump
  // to the nearest selected neighbour. Unselected traces are reached from
  // the collapsed list below.
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
</script>

<div>
  <!-- Review progress: the save gate needs `review_target_count` traces. -->
  <div class="text-sm text-gray-500 mb-4 text-center">
    Reviewed <span class="font-medium text-base-content">{reviewed_count}</span>
    of {review_target_count} required
    {#if unselected.length > 0}
      <span class="text-gray-400">
        — {unselected.length} more conversations below are optional</span
      >
    {/if}
  </div>

  <!-- Jump-to dots: one per SELECTED trace, colored by review state and
       labelled with the trace's conversation number. -->
  <div class="flex items-center mb-10 px-12">
    {#each selected as trace_index, position}
      {@const done = is_trace_reviewed(
        traces[trace_index],
        verdicts[trace_index],
      )}
      {#if position > 0}
        <div class="flex-1 h-0.5 bg-base-300 mx-1"></div>
      {/if}
      <div class="relative flex-none">
        <button
          type="button"
          class="block rounded-full transition-all {trace_index ===
          current_index
            ? 'w-3.5 h-3.5 ring-2 ring-primary ring-offset-1'
            : 'w-2.5 h-2.5'} {done
            ? 'bg-success'
            : 'bg-base-300 hover:bg-base-content/40'}"
          on:click={() => (current_index = trace_index)}
          aria-label={`Jump to conversation ${trace_index + 1}`}
          title={`Conversation ${trace_index + 1}`}
        ></button>
        <span
          class="absolute top-full left-1/2 -translate-x-1/2 mt-2 text-xs {trace_index ===
          current_index
            ? 'text-base-content font-medium'
            : 'text-gray-400'}"
        >
          {trace_index + 1}
        </span>
      </div>
    {/each}
  </div>

  {#if current && current_verdicts}
    <!-- Trace header: the judge's verdict + escape hatch to the full trace. -->
    <div class="flex items-center justify-between mb-4">
      <div class="text-sm text-gray-500">
        Conversation {current_index + 1} — judge verdict:
        <!-- The wire verdict is the lowercase enum; uppercasing is display-only. -->
        <span class="font-medium text-base-content"
          >{current.judge_score.toUpperCase()}</span
        >
      </div>
      <button
        class="btn btn-xs btn-ghost"
        on:click={() => current && trace_modal?.open_trace(current)}
      >
        View full trace
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
          />
        {/if}
      </div>
    {:else if current.claims_state === "error"}
      <Warning
        warning_color="error"
        warning_message={`Couldn't distill this conversation into claims: ${
          current.claims_error ?? "unknown error"
        }`}
      />
      <div class="text-center py-4">
        <button
          class="btn btn-sm btn-primary"
          on:click={() => on_open_trace(current_index)}
        >
          Retry →
        </button>
      </div>
    {:else}
      <!-- "unbuilt" | "building" — the build starts on open, so both render
           as in-progress. -->
      <div class="text-center py-12 text-gray-500">
        <div class="loading loading-dots loading-md mb-2"></div>
        <div class="text-sm">
          Distilling this conversation into claims to review…
        </div>
      </div>
    {/if}
  {/if}

  <!-- Bottom bar: step actions outside, intra-step nav in the middle. -->
  <div class="flex items-center justify-between mt-8 gap-2 flex-wrap">
    <button class="btn btn-sm btn-ghost" on:click={on_back}>← Back</button>
    <div class="flex gap-2">
      <button
        class="btn btn-sm btn-ghost"
        on:click={go_prev}
        disabled={!has_prev}>← Prev</button
      >
      <button
        class="btn btn-sm btn-ghost"
        on:click={go_next}
        disabled={!has_next}>Next →</button
      >
    </div>
    <div class="tooltip tooltip-top" data-tip={save_disabled_tooltip}>
      <button
        class="btn btn-primary"
        on:click={on_save}
        disabled={save_disabled}>Save →</button
      >
    </div>
  </div>

  {#if unselected.length > 0}
    <!-- The unselected remainder: visible and ratable, collapsed by default.
         Reviewing them is optional — extra ratings strengthen the answer key. -->
    <details class="mt-10">
      <summary class="cursor-pointer text-sm text-gray-500">
        More conversations ({unselected.length}) — optional
      </summary>
      <div class="mt-3 divide-y rounded-lg border">
        {#each unselected as trace_index}
          {@const done = is_trace_reviewed(
            traces[trace_index],
            verdicts[trace_index],
          )}
          <div
            class="flex items-center justify-between px-4 py-2 text-sm {trace_index ===
            current_index
              ? 'bg-base-200'
              : ''}"
          >
            <div class="min-w-0">
              <span class="font-medium">Conversation {trace_index + 1}</span>
              {#if done}
                <span class="badge badge-success badge-sm ml-2">reviewed</span>
              {/if}
            </div>
            <button
              class="btn btn-xs btn-ghost text-primary"
              on:click={() => (current_index = trace_index)}
            >
              Review
            </button>
          </div>
        {/each}
      </div>
    </details>
  {/if}
</div>

<ClaimTraceModal bind:this={trace_modal} />

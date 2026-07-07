<script lang="ts">
  // Claim/Evidence review step — one trace at a time. The reviewer answers a
  // few questions (agree/disagree on distilled claims) without reading the
  // trace, opening a [n] citation into the trace modal only for the hard calls.
  // Replaces the read-the-whole-trace pass/fail review.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import {
    is_trace_reviewed,
    type Citation,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"

  export let traces: TraceClaims[]
  // Two-way bound so the parent reads verdicts at save time.
  export let verdicts: TraceReview[]
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

  $: total = traces.length
  $: current = traces[current_index]
  $: current_verdicts = verdicts[current_index]

  // Keep original indices, since verdicts are positional.
  $: visible = (current?.claims ?? [])
    .map((claim, index) => ({ claim, index }))
    .slice(0, MAX_CLAIMS - 1)

  function open_citation(citation: Citation) {
    if (current) trace_modal?.open_citation(current, citation)
  }

  function go_prev() {
    if (current_index > 0) current_index -= 1
  }
  function go_next() {
    if (current_index < total - 1) current_index += 1
  }
</script>

<div>
  <!-- Jump-to dots: one per trace, colored by review state. -->
  <div class="flex items-center mb-10 px-12">
    {#each traces as trace, i}
      {@const done = is_trace_reviewed(trace, verdicts[i])}
      {#if i > 0}
        <div class="flex-1 h-0.5 bg-base-300 mx-1"></div>
      {/if}
      <div class="relative flex-none">
        <button
          type="button"
          class="block rounded-full transition-all {i === current_index
            ? 'w-3.5 h-3.5 ring-2 ring-primary ring-offset-1'
            : 'w-2.5 h-2.5'} {done
            ? 'bg-success'
            : 'bg-base-300 hover:bg-base-content/40'}"
          on:click={() => (current_index = i)}
          aria-label={`Jump to trace ${i + 1}`}
          title={`Trace ${i + 1}`}
        ></button>
        <span
          class="absolute top-full left-1/2 -translate-x-1/2 mt-2 text-xs {i ===
          current_index
            ? 'text-base-content font-medium'
            : 'text-gray-400'}"
        >
          {i + 1}
        </span>
      </div>
    {/each}
  </div>

  {#if current && current_verdicts}
    <!-- Trace header: the judge's verdict + escape hatch to the full trace. -->
    <div class="flex items-center justify-between mb-4">
      <div class="text-sm text-gray-500">
        Judge verdict:
        <span class="font-medium text-base-content">{current.judge_score}</span>
      </div>
      <button
        class="btn btn-xs btn-ghost"
        on:click={() => current && trace_modal?.open_trace(current)}
      >
        View full trace
      </button>
    </div>

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
      <ClaimCard
        claim={current.final_judgement}
        bind:verdict={current_verdicts.final_judgement_verdict}
        on_cite={open_citation}
      />
    </div>
  {/if}

  <!-- Bottom bar: step actions outside, intra-step nav in the middle. -->
  <div class="flex items-center justify-between mt-8 gap-2 flex-wrap">
    <button class="btn btn-sm btn-ghost" on:click={on_back}>← Back</button>
    <div class="flex gap-2">
      <button
        class="btn btn-sm btn-ghost"
        on:click={go_prev}
        disabled={current_index === 0}>← Prev</button
      >
      <button
        class="btn btn-sm btn-ghost"
        on:click={go_next}
        disabled={current_index === total - 1}>Next →</button
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
</div>

<ClaimTraceModal bind:this={trace_modal} />

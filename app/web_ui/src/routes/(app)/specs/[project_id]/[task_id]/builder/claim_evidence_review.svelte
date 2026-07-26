<script lang="ts">
  // Claim/Evidence review step — one trace at a time, BLIND and two-phase.
  //
  // Phase 1: the reviewer reads the transcript and gives their own pass/fail
  // verdict with NO judge signal on screen (no verdict, no reasoning, no
  // claims) — the judge must not anchor the human it's calibrated against.
  // Phase 2 (after the verdict): the judge's verdict, reasoning, and
  // distilled claims appear as a cross-check; a verdict that contradicts the
  // judge needs a reason (that disagreement feeds judge refinement).
  //
  // Subset review: `selected_indices` is the judge-stratified default set the
  // reviewer is asked to grade (the golden answer key's size); the remaining
  // traces sit collapsed below — visible and ratable, just not required.
  // Claims build lazily (multi-turn): opening a trace triggers its build via
  // `on_open_trace` — usually done by the time the reviewer has read the
  // transcript and decided.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import {
    apply_human_verdict,
    is_trace_reviewed,
    reviewed_trace_count,
    type Citation,
    type ExpectedResult,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"

  export let traces: TraceClaims[]
  // Two-way bound so the parent reads verdicts at save time.
  export let verdicts: TraceReview[]
  // Multi-turn traces carry the whole conversation in raw_output (canonical
  // transcript); single-turn traces are an I/O pair shown as two blocks.
  export let multi_turn = false
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

  // Record the blind verdict (or a change of mind in phase 2) and map it
  // onto the agree/disagree wire shape.
  function set_human_verdict(verdict: ExpectedResult) {
    if (!current || !current_verdicts) return
    verdicts[current_index] = apply_human_verdict(
      current,
      current_verdicts,
      verdict,
    )
    verdicts = verdicts
  }

  $: judge_matches_human =
    current_verdicts?.human_verdict !== null &&
    current_verdicts?.human_verdict === current?.judge_score
  $: needs_mismatch_reason =
    current_verdicts?.final_judgement_verdict.agrees === false &&
    !current_verdicts?.final_judgement_verdict.why.trim()
  $: trace_noun = multi_turn ? "Conversation" : "Example"

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
          aria-label={`Jump to ${trace_noun.toLowerCase()} ${trace_index + 1}`}
          title={`${trace_noun} ${trace_index + 1}`}
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
    <!-- Trace header. NO judge signal before the reviewer's own verdict. -->
    <div class="flex items-center justify-between mb-4">
      <div class="text-sm text-gray-500">
        {trace_noun}
        {current_index + 1}
      </div>
      <button
        class="btn btn-xs btn-ghost"
        on:click={() => current && trace_modal?.open_trace(current)}
      >
        View full trace
      </button>
    </div>

    {#if current_verdicts.human_verdict === null}
      <!-- ── Phase 1 — the blind call. The reviewer's own pass/fail over
           the raw content. Nothing judge-derived is on screen. -->
      {#if multi_turn}
        <div
          class="rounded-lg border bg-base-100 px-4 py-3 text-sm whitespace-pre-wrap max-h-[50vh] overflow-y-auto"
        >
          {current.raw_output}
        </div>
      {:else}
        <div class="space-y-3">
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
              Input
            </div>
            <div
              class="rounded-lg border bg-base-100 px-4 py-3 text-sm whitespace-pre-wrap max-h-[25vh] overflow-y-auto"
            >
              {current.raw_input}
            </div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
              Output
            </div>
            <div
              class="rounded-lg border bg-base-100 px-4 py-3 text-sm whitespace-pre-wrap max-h-[35vh] overflow-y-auto"
            >
              {current.raw_output}
            </div>
          </div>
        </div>
      {/if}
      <div class="mt-6 text-center">
        <div class="font-medium mb-3">
          Does this {trace_noun.toLowerCase()} meet your spec?
        </div>
        <div class="flex justify-center gap-3">
          <button
            class="btn btn-outline btn-success"
            on:click={() => set_human_verdict("pass")}
          >
            Pass — meets the spec
          </button>
          <button
            class="btn btn-outline btn-error"
            on:click={() => set_human_verdict("fail")}
          >
            Fail — violates the spec
          </button>
        </div>
      </div>
    {:else}
      <!-- ── Phase 2 — the reveal. Judge verdict + claims as cross-check. -->
      <div class="rounded-lg border p-4 bg-base-100 mb-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="text-sm">
            You said
            <!-- The wire verdict is the lowercase enum; uppercasing is display-only. -->
            <span class="font-semibold"
              >{current_verdicts.human_verdict.toUpperCase()}</span
            >
            — the judge
            {#if judge_matches_human}
              <span class="font-semibold text-success">agreed</span>.
            {:else}
              said
              <span class="font-semibold text-error"
                >{current.judge_score.toUpperCase()}</span
              >.
            {/if}
          </div>
          <div class="flex items-center gap-2 text-xs text-gray-500">
            Change your verdict:
            <button
              class="btn btn-xs {current_verdicts.human_verdict === 'pass'
                ? 'btn-success'
                : 'btn-outline'}"
              on:click={() => set_human_verdict("pass")}
            >
              Pass
            </button>
            <button
              class="btn btn-xs {current_verdicts.human_verdict === 'fail'
                ? 'btn-error'
                : 'btn-outline'}"
              on:click={() => set_human_verdict("fail")}
            >
              Fail
            </button>
          </div>
        </div>
        <p class="text-sm text-gray-600 mt-2 leading-relaxed">
          {current.judge_reasoning}
        </p>
        {#if current_verdicts.final_judgement_verdict.agrees === false}
          <textarea
            class="textarea textarea-bordered textarea-sm w-full mt-3 {needs_mismatch_reason
              ? 'textarea-error'
              : ''}"
            placeholder="Why is the judge wrong here? This refines the eval."
            bind:value={current_verdicts.final_judgement_verdict.why}
            rows="2"
          ></textarea>
        {/if}
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
          <!-- The judge's overall conclusion, pinned last. Read-only: its
               grade IS the reviewer's verdict above, mapped client-side. -->
          {#if current.final_judgement}
            <ClaimCard
              claim={current.final_judgement}
              readonly
              on_cite={open_citation}
            />
          {/if}
        </div>
      {:else if current.claims_state === "error"}
        <Warning
          warning_color="warning"
          warning_message={`Couldn't distill this conversation into claims: ${
            current.claims_error ?? "unknown error"
          }. Your verdict still counts — retry for the claim cross-check.`}
        />
        <div class="text-center py-2">
          <button
            class="btn btn-sm btn-ghost text-primary"
            on:click={() => on_open_trace(current_index)}
          >
            Retry claims →
          </button>
        </div>
      {:else}
        <!-- "unbuilt" | "building" — the build starts on open, so both
             render as in-progress. -->
        <div class="text-center py-6 text-gray-500">
          <div class="loading loading-dots loading-md mb-2"></div>
          <div class="text-sm">
            Distilling the conversation into claims to cross-check…
          </div>
        </div>
      {/if}

      <details class="mt-4">
        <summary class="cursor-pointer text-sm text-gray-500">
          {multi_turn ? "Transcript" : "Input & output"}
        </summary>
        {#if !multi_turn}
          <div
            class="mt-2 rounded-lg border bg-base-100 px-4 py-3 text-sm whitespace-pre-wrap max-h-[25vh] overflow-y-auto"
          >
            {current.raw_input}
          </div>
        {/if}
        <div
          class="mt-2 rounded-lg border bg-base-100 px-4 py-3 text-sm whitespace-pre-wrap max-h-[40vh] overflow-y-auto"
        >
          {current.raw_output}
        </div>
      </details>
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
              <span class="font-medium">{trace_noun} {trace_index + 1}</span>
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

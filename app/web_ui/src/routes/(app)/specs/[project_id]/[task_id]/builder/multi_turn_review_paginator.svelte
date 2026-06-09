<script lang="ts" context="module">
  export type ChainTurn = { role: "user" | "assistant"; content: string }
  export type ReviewChain = {
    case_index: number
    persona_summary: string
    total_cost: number
    trace: ChainTurn[]
  }
  export type ChainVerdict = {
    verdict: "pass" | "fail" | null
    feedback: string
  }
</script>

<script lang="ts">
  export let chains: ReviewChain[]
  // Two-way bound so the parent can read final verdicts at save time.
  export let verdicts: ChainVerdict[]
  // Step-level actions handled by the parent. Wired into the paginator's
  // bottom action bar so we render one bottom row instead of two
  // visually-identical rows stacked.
  export let on_back: () => void = () => {}
  export let on_save: () => void = () => {}
  export let save_disabled: boolean = true
  // Optional tooltip shown when Save is disabled so the user knows why.
  export let save_disabled_tooltip: string | null = null
  // Internal cursor. 0-indexed.
  let current_index = 0

  $: total = chains.length
  $: current_chain = chains[current_index]
  $: current_verdict = verdicts[current_index]
  // Fail without a reason is just noise — the judge prompt needs the WHY,
  // not just the verdict. The parent gates Save on this same condition.
  $: current_needs_reason =
    current_verdict?.verdict === "fail" && !current_verdict.feedback.trim()

  let feedback_input: HTMLInputElement | null = null

  function set_verdict(value: "pass" | "fail") {
    verdicts[current_index] = { ...verdicts[current_index], verdict: value }
    verdicts = verdicts
    // Pass auto-advances — feedback is optional, no friction. Fail keeps the
    // user on the current case and focuses the feedback input so they can
    // type the reason without an extra click.
    if (value === "fail") {
      setTimeout(() => feedback_input?.focus(), 0)
      return
    }
    const next_pending = next_pending_index(current_index)
    if (next_pending !== null) {
      current_index = next_pending
    } else if (current_index < total - 1) {
      current_index += 1
    }
  }

  function next_pending_index(from: number): number | null {
    for (let i = from + 1; i < total; i++) {
      if (verdicts[i]?.verdict === null) return i
    }
    for (let i = 0; i <= from; i++) {
      if (verdicts[i]?.verdict === null) return i
    }
    return null
  }

  function go_prev() {
    if (current_index > 0) current_index -= 1
  }
  function go_next() {
    if (current_index < total - 1) current_index += 1
  }
</script>

<div>
  <!-- Jump-to row — small filled dots connected by solid segments.
       Number labels sit absolutely below each dot so the dots stay
       inline with the connector while still being identifiable. -->
  <div class="flex items-center mb-10 px-12">
    {#each chains as _, i}
      {@const v = verdicts[i]}
      {@const fail_missing_reason = v?.verdict === "fail" && !v.feedback.trim()}
      {#if i > 0}
        <div class="flex-1 h-0.5 bg-base-300 mx-1"></div>
      {/if}
      <div class="relative flex-none">
        <button
          type="button"
          class="block rounded-full transition-all {i === current_index
            ? 'w-3.5 h-3.5 ring-2 ring-primary ring-offset-1'
            : 'w-2.5 h-2.5'} {v?.verdict === 'pass'
            ? 'bg-success'
            : v?.verdict === 'fail'
              ? `bg-error ${fail_missing_reason ? 'ring-2 ring-warning ring-offset-1' : ''}`
              : 'bg-base-300 hover:bg-base-content/40'}"
          on:click={() => (current_index = i)}
          aria-label={`Jump to conversation ${i + 1}`}
          title={`Conversation ${i + 1}`}
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

  <!-- Focused conversation. Persona summary + verdict buttons share
       the top row of the card so the buttons stay above the trace —
       the feedback input that appears below the trace doesn't push
       the buttons down, keeping a stable click target for fast review. -->
  {#if current_chain}
    <div class="card bg-base-200 shadow-sm">
      <div class="card-body p-4">
        <div class="flex items-start justify-between gap-3 mb-4">
          <div class="text-xs text-gray-500 italic flex-1 min-w-0">
            {#if current_chain.persona_summary}
              Persona: {current_chain.persona_summary}
            {/if}
          </div>
          <div class="flex gap-2 flex-none">
            <button
              class="btn btn-sm btn-error {current_verdict?.verdict === 'fail'
                ? ''
                : 'btn-outline'}"
              on:click={() => set_verdict("fail")}
            >
              ✗ Fail
            </button>
            <button
              class="btn btn-sm btn-success {current_verdict?.verdict === 'pass'
                ? ''
                : 'btn-outline'}"
              on:click={() => set_verdict("pass")}
            >
              ✓ Pass
            </button>
          </div>
        </div>
        <div class="space-y-3 text-sm">
          {#each current_chain.trace as turn}
            <div
              class="rounded px-4 py-3 {turn.role === 'user'
                ? 'bg-base-100'
                : 'bg-primary/10'}"
            >
              <div class="text-xs text-gray-500 mb-1">{turn.role}</div>
              <div class="whitespace-pre-wrap">{turn.content}</div>
            </div>
          {/each}
        </div>

        <!-- Feedback only appears once a verdict is set. Required for
             fail so the judge prompt has the reason to learn from;
             optional for pass. Wording mirrors v1's review_examples. -->
        {#if current_verdict?.verdict !== null}
          <input
            type="text"
            class="input input-bordered input-sm mt-4 {current_needs_reason
              ? 'input-error'
              : ''}"
            placeholder={current_verdict?.verdict === "fail"
              ? "Describe why this fails"
              : "Describe why this passes (optional)"}
            bind:value={verdicts[current_index].feedback}
            bind:this={feedback_input}
          />
          <p class="text-xs text-gray-500 mt-1">
            {current_verdict?.verdict === "fail"
              ? "Required. Detailed explanations will improve the judge."
              : "Detailed explanations will improve the judge."}
          </p>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Bottom action bar — step actions (Back / Save) sit outside, the
       intra-step nav (Prev / Next) sits in the middle. Single row so
       the user sees one set of buttons, not two. -->
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

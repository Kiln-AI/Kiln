<script lang="ts">
  // One claim in the Claim/Evidence review — to the reviewer it's just a
  // question to answer: the atomic statement, its one-sentence evidence with
  // clickable [n] citations into the trace, and agree/disagree (+ a required
  // reason on disagree, which feeds the refine loop). Same mechanics for
  // claims and the final judgement — expected_result is server-side signal
  // the reviewer doesn't need to see.
  import {
    type Citation,
    type Claim,
    type ClaimVerdict,
  } from "./claim_evidence"

  export let claim: Claim
  export let verdict: ClaimVerdict
  export let on_cite: (citation: Citation) => void = () => {}
  // The final-judgement variant: visibly the conclusion, not another claim.
  // The card leads with a plain deterministic statement ("The judge failed
  // this conversation") built from expected_result, which the server pins to
  // the judge's real score — the verdict's direction never depends on parsing
  // model prose. The model's own conclusion text is demoted to the reason,
  // and the evidence line is dropped: it re-summarizes the claims the
  // reviewer just graded (except when the verdict is the WHOLE review —
  // claims can be empty for simple evals — where its citations are the only
  // receipts). The claims above stay verdict-blind.
  export let is_final_judgement = false
  // What the judge judged, in the caller's vocabulary: "conversation" for
  // multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // True when the verdict is the only card (empty claims list).
  export let sole_card = false

  // The model's conclusion opens with an "Eval fails — " style prefix, and
  // about half the time (per the capture corpus) it's the BARE verdict with
  // all substance in the evidence sentence. The deterministic headline
  // already states the verdict, so: strip the prefix; a bare verdict yields
  // NO reason text, and the evidence steps back in as the reason.
  $: final_reason = strip_verdict_prefix(claim.claim)
  function strip_verdict_prefix(text: string): string {
    const stripped = text.replace(/^eval (fails|passes)\s*[—:.-]?\s*/i, "")
    if (stripped.length === 0) return ""
    if (stripped === text) return text
    return stripped.charAt(0).toUpperCase() + stripped.slice(1)
  }

  let why_input: HTMLTextAreaElement | null = null

  type Token =
    | { kind: "text"; value: string }
    | { kind: "cite"; n: number; citation: Citation | undefined }
  // Resolve each citation during tokenization rather than with {@const} in the
  // template — {@const} inside an inline {:else} doesn't scope correctly and
  // leaves the binding undefined at runtime.
  $: tokens = tokenize_evidence(claim.evidence, claim.citations)
  function tokenize_evidence(evidence: string, citations: Citation[]): Token[] {
    const out: Token[] = []
    const re = /\[(\d+)\]/g
    let last = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(evidence)) !== null) {
      if (m.index > last)
        out.push({ kind: "text", value: evidence.slice(last, m.index) })
      const n = Number(m[1])
      out.push({
        kind: "cite",
        n,
        citation: citations.find((c) => c.marker === n),
      })
      last = m.index + m[0].length
    }
    if (last < evidence.length)
      out.push({ kind: "text", value: evidence.slice(last) })
    return out
  }

  function set_agrees(value: boolean) {
    verdict.agrees = value
    verdict = verdict
    if (!value) setTimeout(() => why_input?.focus(), 0)
  }

  $: needs_reason = verdict.agrees === false && !verdict.why.trim()
</script>

<div
  class="rounded-lg border p-4 bg-base-100 {is_final_judgement
    ? 'border-primary/40'
    : ''}"
>
  <div class="flex items-start justify-between gap-3">
    <div class="font-medium text-sm min-w-0">
      {#if is_final_judgement}
        The judge
        <span class="font-semibold"
          >{claim.expected_result === "fail" ? "failed" : "passed"}</span
        >
        this {judged_noun}
      {:else}
        {claim.claim}
      {/if}
    </div>
    <div class="flex gap-2 flex-none">
      <button
        class="btn btn-xs {verdict.agrees === true
          ? 'btn-success'
          : 'btn-outline'}"
        on:click={() => set_agrees(true)}
      >
        Agree
      </button>
      <button
        class="btn btn-xs {verdict.agrees === false
          ? 'btn-error'
          : 'btn-outline'}"
        on:click={() => set_agrees(false)}
      >
        Disagree
      </button>
    </div>
  </div>

  {#if is_final_judgement && final_reason}
    <!-- The model's conclusion, demoted to the verdict's reason. -->
    <p class="text-sm text-gray-600 mt-2 leading-relaxed">{final_reason}</p>
  {/if}
  {#if !is_final_judgement || sole_card || !final_reason}
    <!-- Evidence: one sentence with inline [n] chips that open the trace modal. -->
    <p class="text-sm text-gray-600 mt-2 leading-relaxed">
      {#each tokens as token}
        {#if token.kind === "text"}{token.value}{:else if token.citation}<button
            type="button"
            class="align-super text-xs text-primary hover:underline font-medium mx-0.5"
            on:click={() => token.citation && on_cite(token.citation)}
            title="View in trace">[{token.n}]</button
          >{:else}<span class="align-super text-xs text-gray-400"
            >[{token.n}]</span
          >{/if}
      {/each}
    </p>
  {/if}

  {#if verdict.agrees === false}
    <textarea
      class="textarea textarea-bordered textarea-sm w-full mt-3 {needs_reason
        ? 'textarea-error'
        : ''}"
      placeholder="Why do you disagree? This refines the eval."
      bind:value={verdict.why}
      bind:this={why_input}
      rows="2"
    ></textarea>
  {/if}
</div>

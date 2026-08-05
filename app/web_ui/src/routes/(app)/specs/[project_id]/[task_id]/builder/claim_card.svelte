<script lang="ts">
  // One claim in the Claim/Evidence review — to the reviewer it's just a
  // question to answer: the atomic statement, its one-sentence evidence with
  // clickable [n] citations into the trace, and Correct/Incorrect (+ a
  // required reason on Incorrect, which feeds the refine loop). Same grading
  // mechanics for claims and the final judgement; regular claims never
  // surface expected_result (the final-judgement headline does — see below).
  import {
    final_judgement_reason,
    type Citation,
    type Claim,
    type ClaimVerdict,
  } from "./claim_evidence"

  export let claim: Claim
  export let verdict: ClaimVerdict
  export let on_cite: (citation: Citation) => void = () => {}
  // The final-judgement variant: visibly the conclusion, not another claim.
  // The card leads with a plain deterministic statement ("Overall: this
  // conversation failed") built from expected_result, which the server pins
  // to the judge's real score — the verdict's direction never depends on
  // parsing model prose. The model's own conclusion text is demoted to the
  // reason, and the evidence line is dropped: it re-summarizes the claims
  // the reviewer just graded (except when the verdict is the WHOLE review —
  // claims can be empty for simple evals — where its citations are the only
  // receipts). The claims above stay verdict-blind in their text; the
  // card's tint does telegraph the verdict, an accepted trade of the
  // agent-not-judge framing.
  export let is_final_judgement = false
  // What the judge judged, in the caller's vocabulary: "conversation" for
  // multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // True when the verdict is the only card (empty claims list).
  export let sole_card = false

  // The reason under the headline: the claim builder's contract makes this
  // the substantive reason-only line, "" when there is nothing beyond the
  // claims — the exact trigger for the evidence fallback below.
  $: final_reason = final_judgement_reason(claim.claim)

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
    // Agreeing hides the reason box — clear any text typed while disagreeing
    // so the user submits exactly what they see. A stale why would otherwise
    // ride the agree grade into the persisted review and judge refinement.
    if (value) verdict.why = ""
    verdict = verdict
    if (!value) setTimeout(() => why_input?.focus(), 0)
  }

  $: needs_reason = verdict.agrees === false && !verdict.why.trim()
</script>

<!-- The overall card is tinted by verdict — the house callout surface
     (border border-{color}/40 bg-{color}/5, the assistant chat's exact
     formula) with only the hue keyed to the verdict, so the conclusion
     reads as a different kind of card than the claims above it. The
     verdict is stated in the headline, so the color adds emphasis, not
     information. -->
<div
  class="rounded-lg border p-4 {is_final_judgement
    ? claim.expected_result === 'fail'
      ? 'bg-warning/5 border-warning/40'
      : 'bg-success/5 border-success/40'
    : 'bg-base-100'}"
>
  <div class="flex items-start justify-between gap-3">
    <div class="font-medium text-sm min-w-0">
      {#if is_final_judgement}
        <!-- Deterministic headline from the server-pinned expected_result —
             the judge is an implementation detail the reviewer doesn't
             need: the question is simply whether the overall call on the
             {judged_noun} was right. House callout formula: the verdict
             color lives in the icon (warning.svelte's exact exclaim/check
             glyphs), the sentence stays neutral in the claim headings'
             typography. -->
        <span class="flex items-center gap-2">
          {#if claim.expected_result === "fail"}
            <svg
              class="w-5 h-5 flex-none text-warning"
              fill="currentColor"
              viewBox="0 0 256 256"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M128,20.00012a108,108,0,1,0,108,108A108.12217,108.12217,0,0,0,128,20.00012Zm0,192a84,84,0,1,1,84-84A84.0953,84.0953,0,0,1,128,212.00012Zm-12-80v-52a12,12,0,1,1,24,0v52a12,12,0,1,1-24,0Zm28,40a16,16,0,1,1-16-16A16.018,16.018,0,0,1,144,172.00012Z"
              />
            </svg>
          {:else}
            <svg
              class="w-5 h-5 flex-none text-success"
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
          {/if}
          <span>
            Overall, this {judged_noun}
            <span class="font-semibold"
              >{claim.expected_result === "fail" ? "failed" : "passed"}</span
            >.
          </span>
        </span>
      {:else}
        {claim.claim}
      {/if}
    </div>
    <!-- Correct/Incorrect (not Agree/Disagree): the reviewer grades each
         statement as right or wrong — lower cognitive load, and it reads
         the same whichever direction the claim points. -->
    <div class="flex gap-2 flex-none">
      <button
        class="btn btn-xs {verdict.agrees === true
          ? 'btn-success'
          : 'btn-outline'}"
        on:click={() => set_agrees(true)}
      >
        Correct
      </button>
      <button
        class="btn btn-xs {verdict.agrees === false
          ? 'btn-error'
          : 'btn-outline'}"
        on:click={() => set_agrees(false)}
      >
        Incorrect
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
      placeholder="Why is this wrong? Your reason helps improve the eval."
      bind:value={verdict.why}
      bind:this={why_input}
      rows="2"
    ></textarea>
  {/if}
</div>

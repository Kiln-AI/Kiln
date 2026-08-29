<script context="module" lang="ts">
  // Instance counter, so a blind card's "Teach the Judge" label points at its
  // own textarea even if two cards are ever mounted at once.
  let blind_card_seq = 0
</script>

<script lang="ts">
  // One claim in the Claim/Evidence review — to the reviewer it's just
  // something to read and push back on: the atomic statement, its
  // one-sentence evidence with clickable [n] citations into the trace, and a
  // single Disagree toggle (+ a required reason once flagged, which feeds the
  // refine loop). Regular claims never surface expected_result (the
  // final-judgement headline does — see below).
  // The final judgement also has a BLIND variant, which asks the pass/fail
  // question with the call withheld — see the `blind` prop.
  import {
    blind_label_agrees,
    blind_label_from_verdict,
    final_judgement_reason,
    type Citation,
    type Claim,
    type ClaimVerdict,
  } from "./claim_evidence"

  export let claim: Claim
  export let verdict: ClaimVerdict
  export let on_cite: (citation: Citation) => void = () => {}
  // Escape hatch to the full trace, rendered only on the final judgement and
  // only when its evidence carries no clickable [n] citation (legacy
  // pre-guarantee data). Undefined for every other card, which renders no
  // link — so non-final consumers are unaffected.
  export let on_view_trace: (() => void) | undefined = undefined
  // The final-judgement variant: visibly the conclusion, not another claim.
  // The card leads with a plain deterministic statement ("Overall: this
  // conversation failed") built from expected_result, which the server pins
  // to the judge's real score — the verdict's direction never depends on
  // parsing model prose. The model's own conclusion text is demoted to the
  // reason, and its evidence sentence renders below through the same
  // tokenizer as the claims, so the server-guaranteed inline [n] citation is
  // clickable into the trace. The claims above stay verdict-blind in their
  // text; the card's tint does telegraph the verdict, an accepted trade of
  // the agent-not-judge framing.
  export let is_final_judgement = false
  // What the judge judged, in the caller's vocabulary: "conversation" for
  // multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // Display-only: the claim, its evidence and its citations render as usual,
  // but the card carries no verdict controls. For surfaces that show claims as
  // reading material while the grade is taken somewhere else — a second
  // writable control for the same verdict lets one grade silently overwrite
  // the other. Defaults to the interactive card.
  export let display_only = false
  // The blind final-judgement variant: the card asks "Does this {judged_noun}
  // pass?" and answers Pass/Fail, with the call itself withheld — no verdict
  // word, no icon, no tint — so nothing anchors the reviewer before they
  // answer. The reason and its cited evidence still render: the conclusion is
  // what's withheld, never the substance the answer is made from. Agreement
  // with the judge is computed from the label (blind_label_agrees), so this
  // writes the same verdict the stated-verdict card writes and the save, gate
  // and refine paths see one shape. Only meaningful with is_final_judgement.
  export let blind = false
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

  // Final card: show its evidence sentence whenever it has one (other cards
  // always show theirs).
  $: final_evidence_shown = is_final_judgement && claim.evidence.trim() !== ""
  // Dedupe: when the demoted reason and the evidence sentence are the same
  // text, render it once through the tokenizer (keeping its [n] chips) rather
  // than printing the sentence twice.
  $: final_evidence_is_reason =
    is_final_judgement &&
    final_reason !== "" &&
    claim.evidence.trim() === final_reason
  // Whether any inline [n] resolves to a citation the reviewer can click.
  $: has_resolvable_citation = tokens.some(
    (t) => t.kind === "cite" && t.citation,
  )
  // Legacy net: the final card's evidence has no clickable citation (no [n],
  // or markers with no match), so offer the trace escape hatch instead — but
  // only when the caller wired one.
  $: show_trace_fallback =
    is_final_judgement && !!on_view_trace && !has_resolvable_citation

  // Blind mode reads the judge's call off the final judgement's
  // expected_result, which the server pins to the judge's real score — the
  // same field the stated-verdict headline is built from.
  $: blind_verdict = is_final_judgement && blind
  const blind_why_id = `claim-card-why-${blind_card_seq++}`
  // The reviewer's label, derived from the stored verdict rather than held
  // separately, so a revisited card shows the label its reviewer already gave.
  $: blind_label = blind_verdict
    ? blind_label_from_verdict(claim.expected_result, verdict.agrees)
    : null
  // The call appears only where the reviewer contradicts it.
  $: blind_mismatch = blind_verdict && !display_only && verdict.agrees === false
  // Keyed off the REVIEWER's label rather than the judge's, since it describes
  // the verdict just given: a "Pass" label on a failed case asks why it passes.
  $: teach_the_judge_placeholder = `Describe why this ${
    blind_label ? "passes" : "fails"
  }. Detailed explanations will improve the judge.`

  // Record the blind label as the same final-judgement verdict the stated
  // card writes: agreement is computed against the judge, never asked.
  function set_blind_label(user_says_pass: boolean) {
    verdict.agrees = blind_label_agrees(claim.expected_result, user_says_pass)
    // Agreeing closes the reveal, so drop any reason typed against the
    // previous label rather than shipping text the reviewer can no longer see.
    if (verdict.agrees) verdict.why = ""
    verdict = verdict
    if (!verdict.agrees) setTimeout(() => why_input?.focus(), 0)
  }

  // A regular claim offers only Disagree: agreeing with one changes nothing
  // downstream. It does not move the review gate (sub-claim verdicts are
  // optional), does not enter the disagreement count that starts a refine
  // round, and does not put the trace in the next round's subset — only a
  // disagreement and its reason travel. Clicking again clears the flag and
  // the reason typed under it.
  function toggle_disagree() {
    if (verdict.agrees === false) {
      verdict.agrees = null
      verdict.why = ""
      verdict = verdict
      return
    }
    set_agrees(false)
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

<!-- House card chrome (card card-bordered shadow-md); claim cards are not
     click targets, so no hover treatment.
     The overall card is tinted by verdict — the house callout surface
     (border border-{color}/40 bg-{color}/5, the assistant chat's exact
     formula) with only the hue keyed to the verdict, so the conclusion
     reads as a different kind of card than the claims above it. The
     verdict is stated in the headline, so the color adds emphasis, not
     information. The blind variant takes the plain claim-card chrome
     instead: a tint keyed to the verdict would answer the card's own
     question before the reviewer does. border-base-300 rides the untinted
     branch instead of the shared class list, a deliberate departure from
     card_style.md's "always use ... border-base-300": sibling border-color
     utilities are all equal-specificity single classes, so the winner is
     decided by generated stylesheet order (Tailwind's own sort), not by
     class order — branching removes that unknowable rather than betting on
     it. -->
<div
  class="card card-bordered shadow-md p-4 {is_final_judgement && !blind_verdict
    ? claim.expected_result === 'fail'
      ? 'bg-warning/5 border-warning/40'
      : 'bg-success/5 border-success/40'
    : 'bg-base-100 border-base-300'}"
>
  <!-- items-center on the blind card: one short question reads aligned beside
       the buttons where a wrapping claim would not. -->
  <div
    class="flex {blind_verdict
      ? 'items-center'
      : 'items-start'} justify-between gap-3"
  >
    <div class="font-medium text-sm min-w-0">
      {#if blind_verdict}
        <!-- Nothing on this card states the call before the reviewer makes
             their own. -->
        Does this {judged_noun} pass?
      {:else if is_final_judgement}
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
    {#if !display_only}
      <div class="flex gap-2 flex-none">
        {#if blind_verdict}
          <!-- Pass/Fail, the same pair the trace-first arm and the spec
               builder's review table answer this question with. -->
          <button
            class="btn btn-sm {blind_label === true
              ? 'btn-success'
              : 'btn-outline'}"
            on:click={() => set_blind_label(true)}
          >
            Pass
          </button>
          <button
            class="btn btn-sm {blind_label === false
              ? 'btn-error'
              : 'btn-outline'}"
            on:click={() => set_blind_label(false)}
          >
            Fail
          </button>
        {:else if is_final_judgement}
          <!-- The stated-verdict card (a failed claims build) still grades a
               claim that names its own conclusion, so it is marked right or
               wrong rather than answered. -->
          <button
            class="btn btn-sm {verdict.agrees === true
              ? 'btn-success'
              : 'btn-outline'}"
            on:click={() => set_agrees(true)}
          >
            Correct
          </button>
          <button
            class="btn btn-sm {verdict.agrees === false
              ? 'btn-error'
              : 'btn-outline'}"
            on:click={() => set_agrees(false)}
          >
            Incorrect
          </button>
        {:else}
          <!-- "Disagree" is the word the payload already stores, so nothing is
               translated between the click and the record, and it states the
               reviewer's stance rather than a property of the agent. The label
               holds still when active: changing the word under the cursor
               makes the stack harder to scan on a second pass, and the reason
               box appearing is unambiguous feedback already. -->
          <button
            class="btn btn-sm {verdict.agrees === false
              ? 'btn-error'
              : 'btn-outline'}"
            on:click={toggle_disagree}
          >
            Disagree
          </button>
        {/if}
      </div>
    {/if}
  </div>

  {#if is_final_judgement && final_reason && !final_evidence_is_reason}
    <!-- The model's conclusion, demoted to the verdict's reason. Skipped when
         it's identical to the evidence sentence (rendered once below). -->
    <p class="text-sm text-gray-600 mt-2 leading-relaxed">{final_reason}</p>
  {/if}
  {#if !is_final_judgement || final_evidence_shown}
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
  {#if show_trace_fallback}
    <!-- No clickable citation to reach the trace, so give a quiet link that
         opens it directly. -->
    <button
      type="button"
      class="text-xs text-primary hover:underline mt-2 self-start"
      on:click={() => on_view_trace?.()}>View Full Trace</button
    >
  {/if}

  {#if blind_mismatch}
    <!-- MISMATCH only: now the call is worth stating, because the reviewer is
         contradicting it. One line and no explanation, since answering already
         released the reason and its cited evidence onto the card above. It
         names the judge, matching the step header and this block's own label,
         and says "scored" because that is the house verb for what a judge
         does. -->
    <div
      class="mt-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3"
    >
      <!-- FormElement's label typography, hand-rolled so the card's own error
           state stays the one in play. The mismatch rides the description slot
           rather than a second heading: one medium line per field is the house
           shape, and the placeholder still states the ask. -->
      <label
        class="text-sm font-medium text-left flex flex-col gap-1 w-full"
        for={blind_why_id}
      >
        <span>Teach the Judge</span>
        <span class="text-xs text-gray-500">
          The judge disagrees. It scored this as a {claim.expected_result ===
          "pass"
            ? "pass"
            : "fail"}.
        </span>
      </label>
      <!-- Names the field explicitly, the way FormElement does on every input
           it renders. Without it the description nested in the label above
           becomes part of this field's accessible name, so a screen reader
           announces the whole mismatch sentence on every focus. -->
      <textarea
        id={blind_why_id}
        aria-label="Teach the Judge"
        class="textarea textarea-bordered textarea-sm w-full mt-2 {needs_reason
          ? 'textarea-error'
          : ''}"
        placeholder={teach_the_judge_placeholder}
        bind:value={verdict.why}
        bind:this={why_input}
        rows="2"
      ></textarea>
    </div>
  {:else if !display_only && !blind_verdict && verdict.agrees === false}
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

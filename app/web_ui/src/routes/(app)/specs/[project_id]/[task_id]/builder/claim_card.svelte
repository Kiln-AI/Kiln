<script lang="ts">
  // One claim in the claim review: one decision the judge made, written so
  // the reviewer can vote on it from the card. The text carries its own
  // evidence, with [n] chips that open the trace at the cited span. The
  // reviewer answers Agree (the judge got this decision right) or Disagree
  // (it got it wrong); a disagreement needs a reason, which feeds judge
  // refinement. Every claim renders through this one card, the verdict claim
  // included: the builder writes the verdict as an ordinary last claim, and
  // the review derives the reviewer's overall call from its grade
  // (human_verdict in claim_evidence.ts). The card never names the judge or
  // its score: everything on it is the builder's text, the verdict claim's
  // "It passes" / "It fails" included.
  import ClaimText from "./claim_text.svelte"
  import {
    split_claim_note,
    type Citation,
    type Claim,
    type ClaimVerdict,
  } from "./claim_evidence"

  export let claim: Claim
  // Position in the review's claim list, shown as "#{index + 1}": the number
  // the builder's own cross-references ("#1") use.
  export let index: number
  export let verdict: ClaimVerdict
  export let on_cite: (citation: Citation) => void = () => {}
  // Whether disagreeing with THIS claim starts a judge refine, computed by
  // the review from claim_triggers_judge_refine. Required, with no default: a
  // card that was never told would quietly promise the reviewer their
  // disagreement changes nothing. The card only says which of the two things
  // a disagree does; it never decides.
  export let triggers_refine: boolean

  let why_input: HTMLTextAreaElement | null = null

  // The trailing "Note:" paragraph renders apart from the claim, muted; the
  // body is everything else.
  $: split = split_claim_note(claim.text)

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
     click targets, so no hover treatment. -->
<div
  id="claim-card-{index}"
  class="card card-bordered shadow-md p-4 bg-base-100 border-base-300"
>
  <div class="flex items-start justify-between gap-3">
    <p class="text-sm min-w-0 leading-relaxed">
      <span class="font-medium text-gray-500 mr-1.5">#{index + 1}</span
      ><ClaimText text={split.body} citations={claim.citations} {on_cite} />
    </p>
    <!-- Agree / Disagree, in the words the payload stores, so nothing is
         translated between the click and the record. The selected side takes
         the same success/error styling as the Pass/Fail pair elsewhere in the
         builder; the label holds still so the stack stays scannable. -->
    <div class="flex gap-2 flex-none">
      <button
        id="claim-agree-{index}"
        class="btn btn-sm {verdict.agrees === true
          ? 'btn-success'
          : 'btn-outline'}"
        on:click={() => set_agrees(true)}
      >
        Agree
      </button>
      <button
        id="claim-disagree-{index}"
        class="btn btn-sm {verdict.agrees === false
          ? 'btn-error'
          : 'btn-outline'}"
        on:click={() => set_agrees(false)}
      >
        Disagree
      </button>
    </div>
  </div>

  {#if split.note !== null}
    <!-- The builder's aside, muted so it reads as context rather than as part
         of the decision being voted on. -->
    <p class="text-sm text-gray-500 mt-2 leading-relaxed" data-claim-note>
      <ClaimText text={split.note} citations={claim.citations} {on_cite} />
    </p>
  {/if}

  {#if verdict.agrees === false}
    <textarea
      id="claim-why-{index}"
      class="textarea textarea-bordered textarea-sm w-full mt-3 {needs_reason
        ? 'textarea-error'
        : ''}"
      placeholder="Why is this wrong? Your reason helps improve the eval."
      bind:value={verdict.why}
      bind:this={why_input}
      rows="2"
    ></textarea>
    <!-- What this disagreement will do, said on the card so the rule is never
         a surprise. A disagreement with the verdict (or with a claim the
         builder tagged as a possible judge error) refines the judge; every
         other one is a note about the judge's reasoning, saved with the eval
         and handed to the refiner as context, and changes no verdict. Same
         size and colour as the card's other helper text. -->
    <p
      class="text-sm text-gray-500 mt-2 leading-relaxed"
      data-refine-consequence
    >
      {#if triggers_refine}
        This will refine the judge.
      {:else}
        Saved as a note. This does not refine the judge.
      {/if}
    </p>
  {/if}
</div>

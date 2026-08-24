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
  //
  // Two content shapes, one screen (is_trace_first_review picks): a short
  // plain-text single-turn output is cheaper to read whole than as claims, so
  // that trace renders inline and the reviewer labels the output blind, with
  // the claims one click behind [View Claims]. Everything else keeps the claim
  // stack with the trace behind [View Full Trace]. Both write the same
  // verdicts, so save, gate and refine see one shape.
  import ClaimCard from "./claim_card.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  // The house chat UI, the same component the trace modal mounts — the
  // trace-first arm puts it on the page instead of behind a button.
  import ChatTrace from "$lib/ui/trace/chat_trace.svelte"
  // The nav row hand-rolls FormContainer's submit button, so it renders the
  // same keyboard hint using the same platform check.
  import { isMacOS } from "$lib/utils/platform"
  import {
    blind_final_judgement,
    blind_label_agrees,
    blind_label_from_verdict,
    final_judgement_reason,
    is_trace_first_review,
    is_trace_reviewed,
    review_trace_messages,
    type Citation,
    type TraceClaims,
    type TraceReview,
  } from "./claim_evidence"
  import type { TraceMessage } from "$lib/types"

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
  // The two task-level halves of the review-shape gate (the third is the
  // trace's own output length). Defaults describe a plain single-turn task,
  // matching judged_noun's default.
  export let is_multi_turn = false
  export let has_output_schema = false
  // True while the reviewer is on the last selected trace — the only position
  // where the primary action renders. Bound out (read-only for the parent) so
  // anything the parent stacks under that action appears only alongside it.
  export let on_last_trace = false

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null
  let claims_dialog: Dialog | null = null
  let blind_why_input: HTMLTextAreaElement | null = null
  // Only one blind row is ever mounted, so a constant id ties its label to its
  // textarea without an index.
  const BLIND_WHY_ID = "trace-first-why"

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

  // ── Trace-first arm ──────────────────────────────────────────────────
  $: trace_first =
    !!current &&
    is_trace_first_review({
      is_multi_turn,
      has_output_schema,
      raw_output: current.raw_output,
    })

  // The demoted claims mount only once the reviewer asks for this trace's
  // claims: a closed dialog still renders its contents, and the claims state
  // the judge's call, which the blind label must not be shown before it is
  // given. Cleared on every move, so each trace is asked for on its own.
  let claims_opened_for: string | null = null
  $: claims_open = !!current && claims_opened_for === current.trace_id
  function open_claims() {
    if (current) claims_opened_for = current.trace_id
    claims_dialog?.show()
  }

  // The messages the inline renderer shows. review_trace_messages throws when
  // a trace carries neither a transcript nor raws; catching it here turns that
  // into a visible error instead of a blank page the reviewer would label.
  $: inline_trace = trace_first && current ? read_trace(current) : null
  function read_trace(t: TraceClaims): {
    messages: TraceMessage[] | null
    error: string | null
  } {
    try {
      return { messages: review_trace_messages(t), error: null }
    } catch (e) {
      return {
        messages: null,
        error: e instanceof Error ? e.message : "This trace can't be shown.",
      }
    }
  }

  // The reviewer's label, derived from the stored verdict rather than held
  // separately: the verdict is what survives navigation, so a label read back
  // from it still shows on Previous instead of resetting to unanswered.
  $: blind_label =
    current && current_verdicts
      ? blind_label_from_verdict(
          current.judge_score,
          current_verdicts.final_judgement_verdict.agrees,
        )
      : null
  // The judge appears only where the reviewer contradicts it.
  $: blind_mismatch = current_verdicts?.final_judgement_verdict.agrees === false
  $: blind_needs_reason =
    blind_mismatch && !current_verdicts.final_judgement_verdict.why.trim()
  // What the reveal reads out under its headline: the final judgement's own
  // sentence, which is the judge's case-specific explanation and carries the
  // clickable [n] citations. judge_reasoning stands in only when no final
  // judgement was built (a failed claims build) or its text is empty — for a
  // judge model that emits no reasoning trace that field is the server's
  // placeholder, not an explanation of this trace.
  $: reveal = current ? judge_reveal(current) : null
  function judge_reveal(t: TraceClaims): {
    text: string
    citations: Citation[]
  } {
    const judgement = t.final_judgement
    const reason = judgement ? final_judgement_reason(judgement.claim) : ""
    if (judgement && reason) {
      return { text: reason, citations: judgement.citations }
    }
    return { text: t.judge_reasoning.trim(), citations: [] }
  }
  // The "Teach the Judge" ask. The block carries no description line, so the
  // placeholder states the whole ask. Keyed off the REVIEWER's label rather
  // than the judge's, since it describes the verdict just given: a "Pass"
  // label on a case the judge failed asks why it passes.
  $: teach_the_judge_placeholder = `Describe why this ${
    blind_label ? "passes" : "fails"
  }. Detailed explanations will improve the judge.`

  // Record the blind label as the shared final-judgement verdict: agreement is
  // computed against the judge, never asked.
  function set_blind_label(user_says_pass: boolean) {
    if (!current || !current_verdicts) return
    const verdict = current_verdicts.final_judgement_verdict
    verdict.agrees = blind_label_agrees(current.judge_score, user_says_pass)
    // Agreeing closes the reveal, so drop any reason typed against the
    // previous label rather than shipping text the reviewer can no longer see.
    if (verdict.agrees) verdict.why = ""
    // Reassign the bound prop so the parent's save gate sees the grade.
    verdicts = verdicts
    if (!verdict.agrees) setTimeout(() => blind_why_input?.focus(), 0)
  }

  // Prev/Next walk the selected sequence. Both drop the claims opt-in: the
  // next trace's claims are its own to ask for, and a revisited trace should
  // not silently carry the previous visit's answer back onto the screen.
  function go_prev() {
    const prior = selected.filter((i) => i < current_index)
    if (prior.length > 0) current_index = prior[prior.length - 1]
    claims_opened_for = null
  }
  function go_next() {
    const later = selected.filter((i) => i > current_index)
    if (later.length > 0) current_index = later[0]
    claims_opened_for = null
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
    <!-- Trace header: just the quiet escape hatch to whichever content the
         gate demoted — the claims on the trace-first arm, the trace on the
         claims-first one. The verdict label stays off this row (the overall
         card carries it, pinned last) and review-order position lives under
         the nav. -->
    <div class="flex items-center justify-end mb-4">
      {#if trace_first}
        <button class="btn btn-xs btn-ghost" on:click={open_claims}>
          View Claims
        </button>
      {:else}
        <button
          class="btn btn-xs btn-ghost"
          on:click={() => current && trace_modal?.open_trace(current)}
        >
          View Full Trace
        </button>
      {/if}
    </div>

    {#if trace_first}
      <!-- TRACE-FIRST: the trace IS the review. Nothing on this screen states
           the judge's call before the reviewer makes their own. -->
      {#if inline_trace?.error}
        <Warning warning_color="error" warning_message={inline_trace.error} />
      {:else if inline_trace?.messages}
        <div class="rounded bg-base-100 border border-base-300 px-4 py-3">
          <ChatTrace trace={inline_trace.messages} />
        </div>

        <!-- The blind label, in claim-card chrome. items-center rather than the
             cards' items-start: one short question reads aligned beside the
             buttons where a wrapping claim would not. -->
        <div
          class="card card-bordered shadow-md p-4 bg-base-100 border-base-300 mt-4"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="font-medium text-sm min-w-0">
              Does this response pass?
            </div>
            <div class="flex gap-2 flex-none">
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
            </div>
          </div>

          {#if blind_mismatch}
            <!-- MISMATCH only: now the judge is worth reading, because the
                 reviewer is contradicting it. The reason is what the refine
                 loop consumes, and the save gate already requires it. -->
            <div
              class="mt-3 rounded-lg border border-warning/40 bg-warning/5 px-4 py-3"
            >
              <!-- One statement rather than verdict-then-quote: the reveal
                   exists because the reviewer just contradicted the judge, so
                   it leads with the disagreement and the explanation below
                   completes the sentence. The word is the JUDGE's verdict, and
                   the sentence closes on a period when there is no explanation
                   to introduce. -->
              <div class="text-sm font-medium">
                The judge disagrees. It thinks this {current.judge_score ===
                "pass"
                  ? "passes"
                  : "fails"}{reveal?.text ? " because:" : "."}
              </div>
              {#if reveal?.text}
                <!-- The explanation, with the judgement's citations appended
                     as [n] chips. A click runs the same open_citation plumbing
                     the claim cards use, but the chips are derived differently
                     on purpose: a card tokenizes the [n] markers written into
                     its evidence sentence, while this shows the claim
                     sentence, which carries no inline markers — so its
                     citations ride at the end as evidence links. -->
                <p class="text-sm text-gray-600 mt-2 leading-relaxed">
                  {reveal.text}{#each reveal.citations as citation, i (i)}<button
                      type="button"
                      class="align-super text-xs text-primary hover:underline font-medium mx-0.5"
                      on:click={() => open_citation(citation)}
                      title="View in trace">[{citation.marker || i + 1}]</button
                    >{/each}
                </p>
              {/if}
              <!-- FormElement's label typography, hand-rolled so the card's
                   own error state stays the one in play. Label only: the
                   placeholder states the ask, so a description line under the
                   label would just say it twice. -->
              <label
                class="text-sm font-medium text-left flex flex-col gap-1 w-full mt-3"
                for={BLIND_WHY_ID}
              >
                <span>Teach the Judge</span>
              </label>
              <textarea
                id={BLIND_WHY_ID}
                class="textarea textarea-bordered textarea-sm w-full mt-2 {blind_needs_reason
                  ? 'textarea-error'
                  : ''}"
                placeholder={teach_the_judge_placeholder}
                bind:value={current_verdicts.final_judgement_verdict.why}
                bind:this={blind_why_input}
                rows="2"
              ></textarea>
            </div>
          {/if}
        </div>
      {/if}
    {:else if current.claims_state === "built"}
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

<ClaimTraceModal bind:this={trace_modal} />

<!-- The claims the trace-first arm demoted, in the same house Dialog the trace
     escape hatch opens. DISPLAY ONLY: the blind row is this arm's single
     grading control. A second writable control for the same judgement, in the
     card's opposite button vocabulary, would let a reviewer flip their verdict
     and wipe the reason they typed without seeing it happen; and a trace-first
     review's refine feed is the final judgement alone by design. -->
<Dialog bind:this={claims_dialog} title="Claims" width="wide">
  {#if claims_open && current && current_verdicts}
    <div class="max-h-[70vh] overflow-y-auto text-left">
      {#if current.claims_state === "built"}
        <div class="space-y-3">
          {#each visible as { claim, index } (index)}
            <ClaimCard
              {claim}
              verdict={current_verdicts.claim_verdicts[index]}
              on_cite={open_citation}
              display_only
            />
          {/each}
          {#if current.final_judgement}
            <ClaimCard
              claim={current.final_judgement}
              verdict={current_verdicts.final_judgement_verdict}
              on_cite={open_citation}
              on_view_trace={() => current && trace_modal?.open_trace(current)}
              is_final_judgement
              {judged_noun}
              display_only
            />
          {/if}
        </div>
      {:else if current.claims_state === "error"}
        <!-- The review itself is unaffected — the blind label already carries
             this trace's grade — but a retry can still recover the claim
             grades the answer key wants. -->
        <Warning
          warning_color="error"
          warning_message={`Couldn't analyze this ${judged_noun}: ${
            current.claims_error ?? "unknown error"
          }`}
        />
        <div class="text-center py-4">
          <button
            class="btn btn-outline btn-primary"
            on:click={() => on_open_trace(current_index)}
          >
            Retry Analysis
          </button>
        </div>
      {:else}
        <div class="text-center py-12 text-gray-500">
          <div class="loading loading-dots loading-md mb-2"></div>
          <div class="text-sm">Analyzing this {judged_noun}…</div>
        </div>
      {/if}
    </div>
  {/if}
</Dialog>

<script lang="ts">
  // Claim review step — one trace at a time. The reviewer reads the Overview,
  // then votes Agree or Disagree on every claim the builder wrote, opening a
  // [n] citation into the trace modal only for the hard calls. Everything on
  // screen is the builder's text: the judge's score and reasoning never
  // render here, since the reviewer's calls are what calibrate the judge.
  //
  // The overall pass/fail call is the verdict claim's grade — the builder
  // writes the verdict as the last claim, and a case without one is not put in
  // front of the reviewer at all (reviewable_subset). Next is gated on the
  // whole trace being graded (is_trace_reviewed).
  //
  // Subset review: `selected_indices` is the judge-stratified sample the
  // reviewer grades (sized to the golden answer key) — the review shows
  // exactly these traces, mirroring the single-turn flow where the user
  // reviews exactly what's presented. Claims build lazily: opening a trace
  // triggers its build via `on_open_trace`, and the panel shows the build in
  // progress until they arrive. A trace whose build already failed is not in
  // this list at all: the claims gate resolves every selected trace before the
  // review opens, and the page drops the failures from the subset.
  import ClaimCard from "./claim_card.svelte"
  import ClaimText from "./claim_text.svelte"
  import ClaimTraceModal from "./claim_trace_modal.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "$lib/ui/output.svelte"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  // The nav row hand-rolls FormContainer's submit button, so it renders the
  // same keyboard hint using the same platform check.
  import { isMacOS } from "$lib/utils/platform"
  import {
    is_trace_reviewed,
    type Citation,
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
  // until the gate is met, then takes the forward slot on the last conversation.
  export let save_disabled = true
  // The primary action's label and optional tooltip, parent-owned so the
  // button can say what the click actually does (a review with disagreements
  // enters a judge-refine round instead of saving).
  export let save_label = "Save"
  export let save_tooltip: string | null = null
  // What the judge judged, in the caller's vocabulary: "conversation" for
  // multi-turn, "example" for single-turn.
  export let judged_noun = "example"
  // True while the reviewer is on the last selected trace — the only position
  // where the primary action renders. Bound out (read-only for the parent) so
  // anything the parent stacks under that action appears only alongside it.
  export let on_last_trace = false
  // The eval's own description, read-only. The review shows what each
  // conversation did but never what the eval asks for, so a reviewer who
  // forgot it can reread it here. Empty or null hides the control.
  export let spec_text: string | null = null

  let current_index = 0
  let trace_modal: ClaimTraceModal | null = null
  let spec_dialog: Dialog | null = null

  $: has_spec_text = (spec_text ?? "").trim().length > 0

  // Names the judge, because the step header does. Claims are the decisions
  // the judge made, the verdict claim included, and the second sentence names
  // the one control every claim carries.
  $: claims_description = `The decisions the judge made about this ${judged_noun}. Agree or disagree with each.`

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
  $: visible = (current?.claims ?? []).map((claim, index) => ({ claim, index }))

  function open_citation(citation: Citation) {
    if (current) trace_modal?.open_citation(current, citation)
  }

  // Previous/Next walk the selected sequence.
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
  $: on_last_trace = !has_next

  // Next is gated on the CURRENT conversation being fully answered, and says
  // so only by being disabled, as every other form in the app does. Save takes
  // the forward slot on the last conversation, but only once the save gate is
  // met.
  $: current_reviewed = is_trace_reviewed(current, current_verdicts)

  // The reviewer's position in the graded sequence, which the step header
  // states. It is the review's only progress readout.
  $: case_position = selected.indexOf(current_index) + 1
</script>

<!-- One vertical stack owns every gap on the step: gap-6 between sections
     (the form rhythm the rest of the app is built on), gap-3 inside one.
     Nothing below sets its own margin, so the spacing is read in one place
     and cannot drift element by element. -->
<div class="flex flex-col gap-6">
  {#if current && current_verdicts}
    <!-- The step header, which also carries the reviewer's position: the
         review is a sequence, and the position belongs with the title rather
         than in a separate line by the buttons. -->
    <SettingsHeader
      title={`Case ${case_position} of ${selected.length}`}
      subtitle="Confirm the judge is aligned to your expectations."
    />

    <!-- The Overview section renders in every state, so the step never
         changes shape between cases: the header and its two escape hatches
         hold still, and only the body underneath differs — the overview when
         the build produced one, the failure and its retry when it did not,
         and the in-panel wait while it is still running. The [n] chips open
         the same trace view the claims do. -->
    <div id="review-overview" class="flex flex-col gap-3">
      <SettingsHeader title="Overview">
        <svelte:fragment slot="actions">
          {#if has_spec_text}
            <!-- The eval text as a second escape hatch, beside the trace
                 one: both open something the reviewer reads and closes. -->
            <button
              id="view-eval"
              class="btn btn-sm"
              on:click={() => spec_dialog?.show()}
            >
              Eval Description
            </button>
          {/if}
          <button
            id="view-full-trace"
            class="btn btn-sm"
            on:click={() => current && trace_modal?.open_trace(current)}
          >
            Full Trace
          </button>
        </svelte:fragment>
      </SettingsHeader>

      {#if current.overview}
        <!-- The read-only surface the rest of the app shows read-only content
             on, with the chips rendered into its slot: Output prints a string
             and cannot carry a clickable citation itself, so the caller
             renders the body and Output keeps the panel and the copy button
             (which copies the plain text passed as raw_output). -->
        <Output raw_output={current.overview.text}>
          <p class="text-sm leading-relaxed">
            <ClaimText
              text={current.overview.text}
              citations={current.overview.citations}
              on_cite={open_citation}
            />
          </p>
        </Output>
      {:else if current.claims_state === "unbuilt" || current.claims_state === "building"}
        <!-- The build starts on open, so both render as in-progress, in the
             body the overview will fill. Named rather than written as "not
             built": a failed build never reaches this component, and if one
             ever did, an honest empty body beats a spinner that never stops. -->
        <div class="text-center py-12 text-gray-500">
          <div class="loading loading-dots loading-md mb-2"></div>
          <div class="text-sm">Analyzing this {judged_noun}…</div>
        </div>
      {/if}
      <!-- Built but with no overview written: the header still labels the
           section and its escape hatches still work, and nothing is invented
           to fill the body. -->
    </div>

    {#if current.claims_state === "built"}
      <!-- The claims are a list of fields, so they sit at the form's
           field-to-field gap, not the tighter gap a claim uses inside itself.
           The section header is the list's first item and takes the same. -->
      <div class="flex flex-col gap-6">
        <SettingsHeader title="Claims" subtitle={claims_description} />
        {#each visible as { claim, index } (index)}
          <ClaimCard
            {claim}
            {index}
            bind:verdict={current_verdicts.claim_verdicts[index]}
            on_cite={open_citation}
          />
        {/each}
      </div>
    {/if}
  {/if}

  <!-- Bottom nav, the last child of the stack at the same section gap:
       Previous on the left, the forward action on the right. Wizard-step
       navigation is the browser's Back/Forward. Previous is hidden rather
       than disabled where there is nothing to go back to; Next is gated on
       finishing the current case. On the last case the same slot becomes the
       save action. -->
  <div class="flex items-center justify-between gap-2">
    {#if has_prev}
      <button class="btn" on:click={go_prev}>Previous</button>
    {:else}
      <div></div>
    {/if}
    {#if has_next}
      <button
        class="btn btn-primary"
        on:click={go_next}
        disabled={!current_reviewed}>Next</button
      >
    {:else if !save_disabled}
      <!-- Last case, gate met: the same slot holds the save. The label is
           parent-owned (Save vs Refine Judge) so it never promises a save that
           a calibration round would intercept. The keyboard hint rides only
           this enabled variant, because the shortcut fires the save action and
           only once the gate is met. -->
      {#if save_tooltip}
        <div class="tooltip tooltip-left" data-tip={save_tooltip}>
          <button class="btn btn-primary" on:click={on_save}>
            {save_label}
            <span class="opacity-80 ml-2 text-xs font-light">
              {#if isMacOS()}
                <span class="tracking-widest">⌘↵</span>
              {:else}
                <span>ctrl ↵</span>
              {/if}
            </span>
          </button>
        </div>
      {:else}
        <button class="btn btn-primary" on:click={on_save}>
          {save_label}
          <span class="opacity-80 ml-2 text-xs font-light">
            {#if isMacOS()}
              <span class="tracking-widest">⌘↵</span>
            {:else}
              <span>ctrl ↵</span>
            {/if}
          </span>
        </button>
      {/if}
    {:else}
      <!-- Last case, gate not met: the same save action, simply disabled. A
           "Next" here would point at nothing, so the slot stays the save
           action throughout. No keyboard hint: the shortcut is gated on the
           same rule as this button. -->
      <button class="btn btn-primary" disabled>
        {save_label}
      </button>
    {/if}
  </div>
</div>

<!-- One trace rendering for both arms: a single-turn run is a conversation of
     one turn, so the modal no longer needs to be told which arm it is on. -->
<ClaimTraceModal bind:this={trace_modal} />

<!-- One eval-level dialog, not one per conversation, so it lives outside the
     per-conversation markup. Wide, because the description is multi-paragraph
     prose that reads as a narrow ribbon at the default width. -->
{#if has_spec_text}
  <Dialog
    bind:this={spec_dialog}
    title="Eval Description"
    width="wide"
    action_buttons={[{ label: "Close", isCancel: true }]}
  >
    <div id="spec-text">
      <Output raw_output={spec_text ?? ""} show_border />
    </div>
  </Dialog>
{/if}

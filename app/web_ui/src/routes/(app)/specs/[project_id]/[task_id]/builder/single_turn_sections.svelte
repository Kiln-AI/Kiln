<script lang="ts">
  // THE single-turn review anatomy, mounted by both surfaces that show one:
  // the inline trace-first review and the trace modal. Two labelled sections,
  // no chat bubbles and no system row.
  //
  //   INPUT   the input as the judge got it, one grey field.
  //   OUTPUT  everything the model did after it. A tool loop renders as the
  //           house linear rows with the final answer already open; anything
  //           that is a single message renders as a plain field, since there
  //           is no sequence for the accordion to order.
  //
  // Citations (the modal only) follow the established rule: while one is
  // active on a section, that section shows the RAW text with the <mark>,
  // because the span's offsets index the raw source. The section goes back to
  // the content-typed rendering the moment the citation clears.
  import Trace from "$lib/ui/trace/trace.svelte"
  import ReviewField from "./review_field.svelte"
  import type { CitationSource, SingleTurnSections } from "./claim_evidence"

  export let sections: SingleTurnSections
  // The active citation, when the surface has one: which section it cites, the
  // raw source text its offsets index, and the resolved span. Null while
  // browsing, and always null on the inline surface, whose citations open the
  // modal rather than marking in place.
  export let cited: {
    source: CitationSource
    text: string
    span: { start: number; end: number }
  } | null = null

  $: input_cited = cited?.source === "input" ? cited : null
  $: output_cited = cited?.source === "output" ? cited : null
</script>

<div class="space-y-4">
  <div data-testid="review-input">
    <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">Input</div>
    <ReviewField
      tone="input"
      content={input_cited ? input_cited.text : sections.input}
      mark={input_cited ? input_cited.span : null}
    />
  </div>

  <div data-testid="review-output">
    <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">Output</div>
    {#if output_cited}
      <!-- Citation wins: the marked span is why the reviewer clicked, and it
           can only be placed in the raw text its offsets index. -->
      <ReviewField
        tone="output"
        content={output_cited.text}
        mark={output_cited.span}
      />
    {:else if sections.output_error}
      <!-- Scoped to this section: the Input above still renders, because an
           input the run recorded must not disappear with the output. -->
      <div class="rounded bg-primary/5 px-4 py-3 text-error">
        {sections.output_error}
      </div>
    {:else if sections.rows}
      <!-- Keyed on the trace: Trace builds its expanded-row state once at
           mount, so moving to another trace has to remount it for the new
           trace's final answer to open. Keying on the trace id rather than the
           row array means a background claims build reassigning the review's
           trace list leaves the reviewer's open rows alone. -->
      {#key sections.trace_id}
        <div class="rounded bg-primary/5 px-4 py-3">
          <Trace
            trace={sections.rows}
            auto_expand_indices={sections.expand_indices}
          />
        </div>
      {/key}
    {:else}
      <ReviewField tone="output" content={sections.output} />
    {/if}
  </div>
</div>

<script lang="ts">
  // Trace modal for Claim/Evidence review. Hidden by default; opened either to
  // view a whole trace or jumped to a specific [n] citation, where it scrolls
  // to and highlights the cited span. "Most people never open the trace" — this
  // is the escape hatch for the hard calls.
  import { tick } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import {
    resolve_citation_span,
    type Citation,
    type CitationSource,
    type TraceClaims,
  } from "./claim_evidence"

  let dialog: Dialog | null = null
  let trace: TraceClaims | null = null
  // The span to highlight, if opened via a citation. Resolved against the
  // source text; null when just browsing the trace.
  let active_source: CitationSource | null = null
  let active_span: { start: number; end: number } | null = null
  let mark_el: HTMLElement | null = null

  function text_for(source: CitationSource): string {
    if (!trace) return ""
    return source === "input" ? trace.raw_input : trace.raw_output
  }

  // Split a source's text into [before, highlight, after] when it's the active
  // span, so the highlight can carry a ref for scroll-into-view.
  function segments(source: CitationSource) {
    const text = text_for(source)
    if (source !== active_source || !active_span) {
      return { before: text, highlight: "", after: "" }
    }
    return {
      before: text.slice(0, active_span.start),
      highlight: text.slice(active_span.start, active_span.end),
      after: text.slice(active_span.end),
    }
  }

  export function open_trace(t: TraceClaims) {
    trace = t
    active_source = null
    active_span = null
    dialog?.show()
  }

  export async function open_citation(t: TraceClaims, citation: Citation) {
    trace = t
    active_source = citation.source
    active_span = resolve_citation_span(text_for(citation.source), citation)
    dialog?.show()
    // Wait for the highlight <mark> to render, then bring it into view.
    await tick()
    mark_el?.scrollIntoView({ block: "center", behavior: "smooth" })
  }

  $: input_seg = trace ? segments("input") : null
  $: output_seg = trace ? segments("output") : null
</script>

<Dialog bind:this={dialog} title="Trace" width="wide">
  {#if trace}
    <div class="space-y-4 text-sm max-h-[70vh] overflow-y-auto">
      <!-- Input -->
      <div>
        <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
          Input
        </div>
        <div class="rounded bg-base-100 px-4 py-3 whitespace-pre-wrap">
          {#if input_seg}
            {input_seg.before}{#if input_seg.highlight}<mark
                bind:this={mark_el}
                class="bg-warning/40 rounded px-0.5">{input_seg.highlight}</mark
              >{/if}{input_seg.after}
          {/if}
        </div>
      </div>

      <!-- Output -->
      <div>
        <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
          Output
        </div>
        <div class="rounded bg-primary/5 px-4 py-3 whitespace-pre-wrap">
          {#if output_seg}
            {output_seg.before}{#if output_seg.highlight}<mark
                bind:this={mark_el}
                class="bg-warning/40 rounded px-0.5"
                >{output_seg.highlight}</mark
              >{/if}{output_seg.after}
          {/if}
        </div>
      </div>
    </div>
  {/if}
</Dialog>

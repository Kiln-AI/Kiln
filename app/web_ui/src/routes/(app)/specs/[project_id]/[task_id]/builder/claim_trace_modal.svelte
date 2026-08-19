<script lang="ts">
  // Trace modal for Claim/Evidence review. Hidden by default; opened either to
  // view a whole trace or jumped to a specific [n] citation, where it scrolls
  // to and highlights the cited span. Most reviewers never need the full
  // trace; this is the escape hatch for hard calls.
  //
  // Multi-turn traces carry the structured conversation, so the OUTPUT side
  // renders in the house chat UI (ChatTrace) with the citation mapped onto the
  // exact message/node. Single-turn and legacy traces (no structure) keep the
  // raw flattened-text view. The INPUT is always the raw opening message, and
  // it's still citable, so its raw panel + <mark> behavior stays either way.
  import { tick } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatTrace from "$lib/ui/trace/chat_trace.svelte"
  import {
    map_output_span_to_trace,
    resolve_citation_span,
    type Citation,
    type CitationSource,
    type TraceClaims,
    type TraceHighlight,
  } from "./claim_evidence"

  let dialog: Dialog | null = null
  let trace: TraceClaims | null = null
  // The active citation, if opened via one. active_span is its resolved span in
  // the raw source text (drives the raw-panel <mark>); active_source tells us
  // which panel it lands in; null when just browsing.
  let active_source: CitationSource | null = null
  let active_span: { start: number; end: number } | null = null
  let active_citation: Citation | null = null
  let mark_el: HTMLElement | null = null

  // Render the structured chat UI when the trace carries the conversation
  // (multi-turn); otherwise fall back to the raw flattened output panel.
  $: use_chat = !!(trace && trace.trace && trace.trace.length > 0)

  function text_for(source: CitationSource): string {
    if (!trace) return ""
    return source === "input" ? trace.raw_input : trace.raw_output
  }

  // Split a raw source's text into [before, highlight, after] when it's the
  // active span, so the highlight can carry a ref for scroll-into-view.
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

  // Map an OUTPUT citation onto the structured trace so ChatTrace can mark the
  // exact node. Null for input citations, legacy traces, or unmappable spans —
  // ChatTrace then renders without a highlight rather than a wrong one.
  $: chat_highlight = compute_chat_highlight(
    trace,
    active_source,
    active_citation,
  )
  function compute_chat_highlight(
    t: TraceClaims | null,
    source: CitationSource | null,
    citation: Citation | null,
  ): TraceHighlight | null {
    if (!t || !t.trace || source !== "output" || !citation) return null
    const span = resolve_citation_span(t.raw_output, citation)
    if (!span) return null
    return map_output_span_to_trace(t.trace, t.raw_output, span)
  }

  export function open_trace(t: TraceClaims) {
    trace = t
    active_source = null
    active_span = null
    active_citation = null
    dialog?.show()
  }

  export async function open_citation(t: TraceClaims, citation: Citation) {
    trace = t
    active_source = citation.source
    active_citation = citation
    active_span = resolve_citation_span(text_for(citation.source), citation)
    dialog?.show()
    // Wait for the raw-panel <mark> to render, then bring it into view. The
    // chat panel scrolls itself (ChatTrace reacts to its highlight prop), so
    // this only matters for the input panel and the legacy raw-output panel.
    await tick()
    mark_el?.scrollIntoView({ block: "center", behavior: "smooth" })
  }

  $: input_seg = trace ? segments("input") : null
  $: output_seg = trace && !use_chat ? segments("output") : null
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
        {#if use_chat && trace.trace}
          <!-- Multi-turn: the real chat UI, with the citation mapped onto its
               exact node (or unhighlighted when just browsing / unmappable). -->
          <div class="rounded bg-primary/5 px-4 py-3">
            <ChatTrace trace={trace.trace} highlight={chat_highlight} />
          </div>
        {:else if output_seg}
          <!-- Single-turn / legacy: the raw flattened output, unchanged. -->
          <div class="rounded bg-primary/5 px-4 py-3 whitespace-pre-wrap">
            {output_seg.before}{#if output_seg.highlight}<mark
                bind:this={mark_el}
                class="bg-warning/40 rounded px-0.5"
                >{output_seg.highlight}</mark
              >{/if}{output_seg.after}
          </div>
        {/if}
      </div>
    </div>
  {/if}
</Dialog>

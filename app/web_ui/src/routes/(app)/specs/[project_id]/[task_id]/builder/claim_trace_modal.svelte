<script lang="ts">
  // Trace modal for Claim/Evidence review. Hidden by default; opened either to
  // view a whole trace or jumped to a specific [n] citation, where it scrolls
  // to and highlights the cited span. Most reviewers never need the full
  // trace; this is the escape hatch for hard calls.
  //
  // Two arms, and the review component tells this one which it is on:
  //
  //   SINGLE-TURN renders the same two sections as the inline review surface
  //   (Input field, Output section) — one shape for one trace, whether it is
  //   read on the page or behind the button. A citation marks inside the
  //   section it cites.
  //
  //   MULTI-TURN renders the conversation in the house chat UI, with the input
  //   in its own panel above and the citation mapped onto the exact chat node.
  //   A trace with no stored structure keeps the raw flattened panels.
  import { tick } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import ChatTrace from "$lib/ui/trace/chat_trace.svelte"
  import SingleTurnSectionsView from "./single_turn_sections.svelte"
  import {
    map_input_span_to_trace,
    map_output_span_to_trace,
    resolve_citation_span,
    single_turn_sections_resolver,
    type Citation,
    type CitationSource,
    type TraceClaims,
    type TraceHighlight,
  } from "./claim_evidence"

  // Which arm the review that mounts this modal is on. The mounting component
  // knows it (it is the same flag that picks the review shape), and a trace
  // cannot be trusted to say: a single-turn tool loop has many messages, and a
  // multi-turn conversation can be two.
  export let single_turn = false

  let dialog: Dialog | null = null
  let trace: TraceClaims | null = null
  let content_el: HTMLElement | null = null
  // The active citation, if opened via one. active_span is its resolved span in
  // the raw source text (drives the <mark>); active_source says which side of
  // the trace it cites; null when just browsing.
  let active_source: CitationSource | null = null
  let active_span: { start: number; end: number } | null = null
  let active_citation: Citation | null = null

  // ── Single-turn ──────────────────────────────────────────────────────
  // The two sections, memoized on the trace content so reopening the dialog on
  // the same trace hands the rows the same array and keeps their expansion.
  // `error` is the trace having nothing to render at all; a missing output
  // alone is reported inside the Output section instead.
  const read_sections = single_turn_sections_resolver()
  $: sections = single_turn && trace ? read_sections(trace) : null

  // The active citation as the sections take it: the raw source its offsets
  // index, the span, and the anchors it resolved from — a field that formats
  // its content re-finds the citation in the formatted body from those. Null
  // while browsing, which is what puts the sections back on their content-typed
  // renderers.
  $: cited =
    trace && active_source && active_span && active_citation
      ? {
          source: active_source,
          text: text_for(active_source),
          span: active_span,
          anchors: active_citation,
        }
      : null

  // ── Multi-turn ───────────────────────────────────────────────────────
  // Render the chat UI when the trace carries the conversation; otherwise fall
  // back to the raw flattened output panel. Both are gated on the arm: the
  // single-turn path renders none of it, and mapping a citation onto chat
  // nodes nothing will draw is work for a highlight that cannot appear.
  $: use_chat =
    !single_turn && !!(trace && trace.trace && trace.trace.length > 0)

  function text_for(source: CitationSource): string {
    if (!trace) return ""
    return source === "input" ? trace.raw_input : trace.raw_output
  }

  // Split a raw source's text into [before, highlight, after] when it's the
  // active span, so the highlight can be marked and scrolled to.
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

  // Map a citation onto the structured trace so ChatTrace can mark the exact
  // node: output citations through the flattener layout, input citations onto
  // the conversation's opening user message (on multi-turn the input IS that
  // message). Null for legacy traces or unmappable spans — ChatTrace then
  // renders without a highlight rather than a wrong one, and the miss is
  // logged so the silence is observable.
  $: chat_highlight = single_turn
    ? null
    : compute_chat_highlight(trace, active_source, active_citation)
  function compute_chat_highlight(
    t: TraceClaims | null,
    source: CitationSource | null,
    citation: Citation | null,
  ): TraceHighlight | null {
    // An empty trace renders the raw panels (which carry their own mark),
    // so it is not a mapping miss and must not warn.
    if (!t || !t.trace || t.trace.length === 0 || !source || !citation) {
      return null
    }
    const raw = source === "input" ? t.raw_input : t.raw_output
    const span = resolve_citation_span(raw, citation)
    let mapped = span
      ? source === "input"
        ? map_input_span_to_trace(t.trace, t.raw_input, span)
        : map_output_span_to_trace(t.trace, t.raw_output, span)
      : null
    if (mapped && !chat_renders_highlight(t.trace, mapped)) {
      // The flattener emits blocks for rows the chat drops (system /
      // developer), so a span can map onto a node ChatTrace will never
      // draw — passing it through would be a highlight with no target.
      mapped = null
    }
    if (!mapped) {
      console.warn(
        "Citation could not be mapped onto the trace; showing it without a highlight.",
        { marker: citation.marker, source, from: citation.from },
      )
    }
    return mapped
  }

  // Whether ChatTrace draws a row that can carry this highlight: tool
  // results render through their owning call's bubble, everything else
  // needs its own row, which system/developer/tool messages never get.
  function chat_renders_highlight(
    trace_messages: NonNullable<TraceClaims["trace"]>,
    h: TraceHighlight,
  ): boolean {
    if (h.kind === "tool_result") return true
    const message = trace_messages[h.trace_index]
    const role =
      message && "role" in message && typeof message.role === "string"
        ? message.role
        : ""
    return role !== "system" && role !== "developer" && role !== "tool"
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
    // Wait for the <mark> to render, then bring it into view. Only the raw
    // marks need this: on multi-turn the chat panel scrolls itself (ChatTrace
    // reacts to its highlight prop).
    await tick()
    content_el
      ?.querySelector("[data-citation-mark]")
      ?.scrollIntoView({ block: "center", behavior: "smooth" })
  }

  // When the chat carries the citation's highlight, the Input panel shows
  // plain text: marking its copy too would put the same sentence on screen
  // twice with two competing scroll targets. The panel's mark survives as
  // the fallback for an input citation the chat could not map.
  $: input_seg =
    trace && !single_turn
      ? use_chat && chat_highlight && active_source === "input"
        ? { before: text_for("input"), highlight: "", after: "" }
        : segments("input")
      : null
  $: output_seg = trace && !single_turn && !use_chat ? segments("output") : null
</script>

<Dialog bind:this={dialog} title="Trace" width="wide">
  {#if trace}
    <div
      class="space-y-4 text-sm max-h-[70vh] overflow-y-auto"
      bind:this={content_el}
    >
      {#if single_turn}
        <!-- SINGLE-TURN: the same two sections the inline review shows. -->
        {#if sections?.error}
          <div class="text-error">{sections.error}</div>
        {:else if sections?.sections}
          <SingleTurnSectionsView sections={sections.sections} {cited} />
        {/if}
      {:else}
        <!-- MULTI-TURN: the input as judged, then the conversation. -->
        <div>
          <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
            Input
          </div>
          <div class="rounded bg-base-100 px-4 py-3 whitespace-pre-wrap">
            {#if input_seg}
              {input_seg.before}{#if input_seg.highlight}<mark
                  data-citation-mark
                  class="bg-warning/40 rounded px-0.5"
                  >{input_seg.highlight}</mark
                >{/if}{input_seg.after}
            {/if}
          </div>
        </div>

        <div>
          <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">
            Output
          </div>
          {#if use_chat && trace.trace}
            <!-- The real chat UI, with the citation mapped onto its exact node
                 (or unhighlighted when just browsing / unmappable). -->
            <div class="rounded bg-primary/5 px-4 py-3">
              <ChatTrace trace={trace.trace} highlight={chat_highlight} />
            </div>
          {:else if output_seg}
            <!-- No structured trace recorded: the raw flattened output. -->
            <div class="rounded bg-primary/5 px-4 py-3 whitespace-pre-wrap">
              {output_seg.before}{#if output_seg.highlight}<mark
                  data-citation-mark
                  class="bg-warning/40 rounded px-0.5"
                  >{output_seg.highlight}</mark
                >{/if}{output_seg.after}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</Dialog>

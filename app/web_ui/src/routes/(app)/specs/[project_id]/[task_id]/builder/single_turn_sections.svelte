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
  // Citations (the modal only) mark IN PLACE: a section keeps the rendering it
  // would have anyway and the cited range is highlighted inside it. On a field
  // the field does that itself; on the rows it needs this component's help,
  // because the row holding the citation has to be OPEN before there is any
  // rendered text to mark (see below). A citation that cannot be placed either
  // way falls back to the raw text with the mark in it.
  import Trace from "$lib/ui/trace/trace.svelte"
  import ReviewField from "./review_field.svelte"
  import { citation_mark } from "./citation_highlight"
  import {
    resolve_citation_span_whitespace_tolerant,
    type Citation,
    type CitationSource,
    type SingleTurnSections,
  } from "./claim_evidence"
  import type { TraceMessage } from "$lib/types"

  export let sections: SingleTurnSections
  // The active citation, when the surface has one: which section it cites, the
  // raw source text its offsets index, the resolved span, and the anchors it
  // resolved from. Null while browsing, and always null on the inline surface,
  // whose citations open the modal rather than marking in place.
  export let cited: {
    source: CitationSource
    text: string
    span: { start: number; end: number }
    anchors: Pick<Citation, "from" | "to">
  } | null = null

  $: input_cited = cited?.source === "input" ? cited : null
  $: output_cited = cited?.source === "output" ? cited : null

  // What a field takes: the anchors to find in its rendered body, plus the raw
  // pair to fall back to.
  //
  // Referentially STABLE across renders where the citation has not changed. The
  // field passes this straight to an action, and an action re-runs whenever its
  // parameter changes identity — a fresh object per render would re-fold and
  // re-walk a five-thousand-character body on every unrelated invalidation of
  // the review page. One resolver per field, since the two hold different
  // citations.
  type FieldCited = {
    anchors: Pick<Citation, "from" | "to">
    raw_text: string
    raw_span: { start: number; end: number }
  }
  function stable_field_cited(): (c: typeof cited) => FieldCited | null {
    let last: typeof cited = null
    let value: FieldCited | null = null
    return (c) => {
      const same =
        (!c && !last) ||
        (!!c &&
          !!last &&
          c.anchors.from === last.anchors.from &&
          c.anchors.to === last.anchors.to &&
          c.text === last.text &&
          c.span.start === last.span.start &&
          c.span.end === last.span.end)
      if (!same) {
        last = c
        value = c
          ? { anchors: c.anchors, raw_text: c.text, raw_span: c.span }
          : null
      }
      return value
    }
  }
  const input_field_cited = stable_field_cited()
  const output_field_cited = stable_field_cited()

  // ── The rows path ────────────────────────────────────────────────────
  // Rows are collapsed by default and render NOTHING until opened, so a
  // citation inside one has no text to mark until its row is open. Which row is
  // found by looking for the citation in each message's content, since a row is
  // what the reviewer is looking at, while the span indexes the raw output.
  //
  // More than one row can hold the same words — a tool result the answer
  // quotes back is the standard case — and the citation is only ever about one
  // of them. The span indexes the RAW output, so the rows whose content appears
  // in that raw output are the ones the span could be pointing at, and the last
  // of those is the answer rather than the work that led to it. A citation no
  // such row holds falls back to the first content match, which is a guess but
  // a better one than nothing. -1 when no row holds it at all.
  function find_cited_row(
    rows: TraceMessage[],
    anchors: Pick<Citation, "from" | "to">,
    raw_text: string,
  ): number {
    const holds = rows
      .map((row, index) => ({ index, content: row_content(row) }))
      .filter(
        ({ content }) =>
          content.length > 0 &&
          resolve_citation_span_whitespace_tolerant(content, anchors) !== null,
      )
    const in_raw = holds.filter(({ content }) => raw_text.includes(content))
    return (in_raw[in_raw.length - 1] ?? holds[0])?.index ?? -1
  }

  function row_content(row: TraceMessage): string {
    return "content" in row && typeof row.content === "string"
      ? row.content
      : ""
  }

  $: cited_row =
    output_cited && sections.rows
      ? find_cited_row(sections.rows, output_cited.anchors, output_cited.text)
      : -1
  // The cited row opens on top of whatever the section opens anyway.
  $: rows_expand =
    cited_row >= 0
      ? [...sections.expand_indices, cited_row]
      : sections.expand_indices
  // Trace reads auto_expand_indices ONCE at mount, so OPENING the cited row is
  // a remount, and a remount throws away every row the reviewer opened by hand.
  // That price buys something when a citation arrives; it buys nothing when one
  // is cleared, so the key only ever advances — it remembers the last row a
  // citation opened and stays there. Clearing then leaves the rows exactly as
  // the reviewer left them, and only the mark goes away.
  let opened_row = -1
  $: if (cited_row >= 0 && cited_row !== opened_row) opened_row = cited_row
  // A trace id and an integer, so a colon joins them unambiguously.
  $: rows_key = `${sections.trace_id}:${opened_row}`

  // Whether the mark went into the rows. False sends the section to the raw
  // field, which is what a cited rows case has always shown.
  let rows_in_place = true
  // Which citation that verdict belongs to, kept as its PARTS. Joining anchors
  // into one key would need a separator, and every candidate separator is a
  // character some model-written anchor is entitled to contain.
  let rows_attempted: { from: string; to: string; key: string } | null = null
  function same_rows_attempt(c: typeof output_cited, key: string): boolean {
    if (!c) return rows_attempted === null
    return (
      !!rows_attempted &&
      rows_attempted.from === c.anchors.from &&
      rows_attempted.to === c.anchors.to &&
      rows_attempted.key === key
    )
  }
  // Every distinct citation gets its own attempt: that the last one was not in
  // the rows says nothing about this one.
  $: if (!same_rows_attempt(output_cited, rows_key)) {
    rows_attempted = output_cited
      ? {
          from: output_cited.anchors.from,
          to: output_cited.anchors.to,
          key: rows_key,
        }
      : null
    rows_in_place = true
  }

  // A citation no row holds cannot be marked in the rows at all — the field
  // fallback takes it without a DOM attempt.
  $: rows_fallback = !!output_cited && (cited_row < 0 || !rows_in_place)

  // The cited row's own content region. Scoped there rather than at the row
  // list because a collapsed row shows a truncated PREVIEW of its message, and
  // an unscoped search would mark some other row's preview instead of the
  // answer being cited. Keyed on the OPENED row, not the cited one, so that
  // clearing a citation can still find the row whose marks need removing.
  function cited_row_body(node: HTMLElement): HTMLElement | null {
    const row = node.querySelectorAll(".collapse-content")[opened_row]
    return row instanceof HTMLElement ? row : null
  }

  function on_rows_result(placed: boolean) {
    if (rows_in_place !== placed) rows_in_place = placed
  }
</script>

<div class="space-y-4">
  <div data-testid="review-input">
    <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">Input</div>
    <ReviewField
      tone="input"
      content={sections.input}
      cited={input_field_cited(input_cited)}
    />
  </div>

  <div data-testid="review-output">
    <div class="text-xs uppercase tracking-wide text-gray-500 mb-1">Output</div>
    {#if sections.output_error}
      <!-- Scoped to this section: the Input above still renders, because an
           input the run recorded must not disappear with the output. -->
      <div class="rounded bg-primary/5 px-4 py-3 text-error">
        {sections.output_error}
      </div>
    {:else if sections.rows && rows_fallback && output_cited}
      <!-- No row holds this citation. The marked span is why the reviewer
           clicked, so the section shows the raw output it does index. -->
      <ReviewField
        tone="output"
        content={output_cited.text}
        cited={output_field_cited(output_cited)}
      />
    {:else if sections.rows}
      <!-- Keyed on the trace and on the last row a citation opened: Trace
           builds its expanded-row state once at mount, so both of those need a
           remount to take effect, and a remount closes whatever the reviewer
           opened by hand. Nothing else is in the key — a background claims
           build reassigning the review's trace list, or a citation being
           cleared, leaves their open rows alone. -->
      {#key rows_key}
        <div
          class="rounded bg-primary/5 px-4 py-3"
          use:citation_mark={{
            citation:
              output_cited && cited_row >= 0 ? output_cited.anchors : null,
            body: rows_key,
            within: cited_row_body,
            on_result: on_rows_result,
          }}
        >
          <Trace trace={sections.rows} auto_expand_indices={rows_expand} />
        </div>
      {/key}
    {:else}
      <ReviewField
        tone="output"
        content={sections.output}
        cited={output_field_cited(output_cited)}
      />
    {/if}
  </div>
</div>

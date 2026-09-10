<script lang="ts">
  // One field of a single-turn review section: a tinted box holding content
  // rendered by what the content IS. Structured output goes through the house
  // Output idiom (pretty-print + syntax highlight), which is how Kiln shows
  // JSON everywhere else; prose goes through the same markdown renderer the
  // chat bubbles use, so bold and lists in a model's answer keep working.
  //
  // Background transparent on the Output idiom: the field owns the tint, and
  // Output's own base-200 panel would paint a second surface on top of it.
  //
  // A citation does NOT change any of that. The field renders the same way
  // cited or not, and the mark is applied to the rendered DOM afterwards (see
  // citation_highlight). The one exception is the fallback below.
  import Output, { is_non_string_json } from "$lib/ui/output.svelte"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import { citation_mark } from "./citation_highlight"
  import type { Citation } from "./claim_evidence"

  export let content: string
  // Which section this field belongs to. Input is the neutral surface, output
  // the primary-tinted one — the same two colors the trace modal has always
  // used for the pair.
  export let tone: "input" | "output" = "input"
  // The active citation on this field, if any: the anchors to find in the
  // rendered body, plus the raw text and the span resolved against it. The raw
  // pair is the fallback — a citation the rendering genuinely does not contain
  // is still marked, in the raw text, rather than dropped.
  export let cited: {
    anchors: Pick<Citation, "from" | "to">
    raw_text: string
    raw_span: { start: number; end: number }
  } | null = null

  // Whether the mark went into the rendered body. False puts the raw fallback
  // on screen, which is the old cited rendering.
  let in_place = true
  // Which citation that verdict belongs to, kept as its PARTS. The surfaces
  // above rebuild the cited object on every render, so the retry cannot key on
  // identity; and joining anchors into one string would need a separator, which
  // every candidate character some model-written anchor is entitled to contain.
  let attempted: { from: string; to: string; content: string } | null = null
  function same_attempt(c: typeof cited, body: string): boolean {
    if (!c) return attempted === null
    return (
      !!attempted &&
      attempted.from === c.anchors.from &&
      attempted.to === c.anchors.to &&
      attempted.content === body
    )
  }

  $: tint = tone === "input" ? "bg-base-200" : "bg-primary/5"
  // Every distinct citation, and every new body, gets its own attempt: that a
  // previous citation was not in the rendering says nothing about this one.
  $: if (!same_attempt(cited, content)) {
    attempted = cited
      ? { from: cited.anchors.from, to: cited.anchors.to, content }
      : null
    in_place = true
  }
  $: fallback = !!cited && !in_place
  $: segments =
    fallback && cited
      ? {
          before: cited.raw_text.slice(0, cited.raw_span.start),
          marked: cited.raw_text.slice(
            cited.raw_span.start,
            cited.raw_span.end,
          ),
          after: cited.raw_text.slice(cited.raw_span.end),
        }
      : null

  // Not in the rendering: re-render into the raw fallback so the reviewer still
  // gets the mark they clicked for. Guarded against re-assigning the same
  // verdict, which the action reports on every render and which would otherwise
  // loop the update cycle.
  function on_result(placed: boolean) {
    if (in_place !== placed) in_place = placed
  }
</script>

<div class="rounded {tint} px-4 py-3 {segments ? 'whitespace-pre-wrap' : ''}">
  {#if segments}
    <!-- Fallback: the anchors are not in the rendered body, so the mark goes
         where the offsets do index — the raw text. Losing the mark the reviewer
         clicked for would be worse than showing it unformatted. -->
    {segments.before}<mark
      data-citation-mark
      class="bg-warning/40 rounded px-0.5">{segments.marked}</mark
    >{segments.after}
  {:else}
    <div
      use:citation_mark={{
        citation: cited ? cited.anchors : null,
        body: content,
        on_result,
      }}
    >
      {#if is_non_string_json(content)}
        <Output
          raw_output={content}
          no_padding={true}
          background_color="transparent"
        />
      {:else if content}
        <ChatMarkdown text={content} />
      {:else}
        <!-- An empty field says so: a bare tinted box reads as a render bug, and
             a reviewer grading a trace needs to know the emptiness IS the
             content. Deliberately not the chat UI's "(empty message)" — this is
             a field holding one side of a trace, not a turn somebody failed to
             send. -->
        <span class="text-gray-400 italic">(empty)</span>
      {/if}
    </div>
  {/if}
</div>

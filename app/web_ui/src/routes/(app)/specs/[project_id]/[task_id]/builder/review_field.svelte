<script lang="ts">
  // One field of a single-turn review section: a tinted box holding content
  // rendered by what the content IS. Structured output goes through the house
  // Output idiom (pretty-print + syntax highlight), which is how Kiln shows
  // JSON everywhere else; prose goes through the same markdown renderer the
  // chat bubbles use, so bold and lists in a model's answer keep working.
  //
  // Background transparent on the Output idiom: the field owns the tint, and
  // Output's own base-200 panel would paint a second surface on top of it.
  import Output, { is_non_string_json } from "$lib/ui/output.svelte"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"

  export let content: string
  // Which section this field belongs to. Input is the neutral surface, output
  // the primary-tinted one — the same two colors the trace modal has always
  // used for the pair.
  export let tone: "input" | "output" = "input"
  // A citation's resolved span, when one is active on this field. Set means
  // the field renders `content` as RAW text with the span marked: the offsets
  // index the raw source the citation resolved against, so a pretty-printed or
  // markdown-rendered body would put the mark somewhere else entirely. The
  // caller passes the raw source as `content` in that case.
  export let mark: { start: number; end: number } | null = null

  $: tint = tone === "input" ? "bg-base-200" : "bg-primary/5"
  $: segments = mark
    ? {
        before: content.slice(0, mark.start),
        marked: content.slice(mark.start, mark.end),
        after: content.slice(mark.end),
      }
    : null
</script>

<div class="rounded {tint} px-4 py-3 {segments ? 'whitespace-pre-wrap' : ''}">
  {#if segments}
    {segments.before}<mark
      data-citation-mark
      class="bg-warning/40 rounded px-0.5">{segments.marked}</mark
    >{segments.after}
  {:else if is_non_string_json(content)}
    <Output
      raw_output={content}
      no_padding={true}
      background_color="transparent"
    />
  {:else if content}
    <ChatMarkdown text={content} />
  {:else}
    <!-- An empty field says so: a bare tinted box reads as a render bug, and a
         reviewer grading a trace needs to know the emptiness IS the content.
         Deliberately not the chat UI's "(empty message)" — this is a field
         holding one side of a trace, not a turn somebody failed to send. -->
    <span class="text-gray-400 italic">(empty)</span>
  {/if}
</div>

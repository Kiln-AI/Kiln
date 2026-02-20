<script lang="ts">
  export let markdown_text: string

  type Segment =
    | { type: "text"; content: string }
    | { type: "bold"; content: string }
    | { type: "link"; text: string; url: string }

  // Parse a line of text into segments for safe rendering
  function parseLineToSegments(text: string): Segment[] {
    const segments: Segment[] = []
    // Combined regex to match links or bold text
    const pattern = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g
    let lastIndex = 0
    let match

    while ((match = pattern.exec(text)) !== null) {
      // Add plain text before this match
      if (match.index > lastIndex) {
        segments.push({
          type: "text",
          content: text.slice(lastIndex, match.index),
        })
      }

      if (match[1] !== undefined && match[2] !== undefined) {
        // Link: [text](url) - match[1] is text, match[2] is url
        segments.push({ type: "link", text: match[1], url: match[2] })
      } else if (match[3] !== undefined) {
        // Bold: **text** - match[3] is the bold content
        segments.push({ type: "bold", content: match[3] })
      }

      lastIndex = pattern.lastIndex
    }

    // Add remaining plain text
    if (lastIndex < text.length) {
      segments.push({ type: "text", content: text.slice(lastIndex) })
    }

    // If no segments were added, return the whole text as plain
    if (segments.length === 0) {
      segments.push({ type: "text", content: text })
    }

    return segments
  }
</script>

{#each markdown_text.replace(/\\n/g, "\n").split("\n") as line}
  {#if line.trim() !== ""}
    <p>
      {#each parseLineToSegments(line) as segment}
        {#if segment.type === "text"}
          {segment.content}
        {:else if segment.type === "bold"}
          <strong>{segment.content}</strong>
        {:else if segment.type === "link"}
          <a
            href={segment.url}
            target="_blank"
            rel="noopener noreferrer"
            class="link"
          >
            {segment.text}
          </a>
        {/if}
      {/each}
    </p>
  {:else}
    <p class="h-2"></p>
  {/if}
{/each}

<script lang="ts" context="module">
  import type { Task, Trace, TraceMessage } from "$lib/types"

  export type RenderedMessage = {
    key: string
    role: "user" | "assistant"
    content: string
    reasoning_content: string | null
    tool_messages: TraceMessage[]
  }

  function flatten_content(c: unknown): string {
    if (typeof c === "string") return c
    if (Array.isArray(c)) {
      return c
        .map((part) => {
          if (
            part &&
            typeof part === "object" &&
            "text" in part &&
            typeof (part as { text: unknown }).text === "string"
          ) {
            return (part as { text: string }).text
          }
          return ""
        })
        .filter((s) => s.length > 0)
        .join("\n")
    }
    return ""
  }

  function has_string_content(message: TraceMessage): boolean {
    return (
      "content" in message &&
      message.content !== null &&
      message.content !== undefined &&
      flatten_content(message.content).length > 0
    )
  }

  function reasoning_from(message: TraceMessage): string | null {
    if (
      "reasoning_content" in message &&
      typeof message.reasoning_content === "string" &&
      message.reasoning_content.length > 0
    ) {
      return message.reasoning_content
    }
    return null
  }

  export function build_rendered_messages(trace: Trace): RenderedMessage[] {
    const out: RenderedMessage[] = []
    let pending_tools: TraceMessage[] = []
    let pending_reasoning: string | null = null
    let index = 0

    for (const message of trace) {
      if (message.role === "system" || message.role === "developer") {
        continue
      }

      if (message.role === "user") {
        out.push({
          key: `m-${index++}`,
          role: "user",
          content: flatten_content(message.content),
          reasoning_content: null,
          tool_messages: [],
        })
        continue
      }

      if (message.role === "assistant") {
        const reasoning = reasoning_from(message)
        if (has_string_content(message)) {
          out.push({
            key: `m-${index++}`,
            role: "assistant",
            content: flatten_content(message.content),
            reasoning_content: reasoning ?? pending_reasoning,
            tool_messages: pending_tools,
          })
          pending_tools = []
          pending_reasoning = null
          continue
        }
        // Assistant with only tool_calls — fold into the pending tool messages
        // so they render inside the next assistant block.
        if (reasoning && !pending_reasoning) {
          pending_reasoning = reasoning
        }
        pending_tools.push(message)
        continue
      }

      if (message.role === "tool" || message.role === "function") {
        pending_tools.push(message)
        continue
      }
    }

    // Trailing tool/reasoning without a closing assistant text — surface them
    // as an empty assistant block so they don't get dropped.
    if (pending_tools.length > 0 || pending_reasoning) {
      out.push({
        key: `m-${index++}`,
        role: "assistant",
        content: "",
        reasoning_content: pending_reasoning,
        tool_messages: pending_tools,
      })
    }

    return out
  }
</script>

<script lang="ts">
  import MessageBlock from "./message_block.svelte"

  export let trace: Trace
  export let task: Task

  $: messages = build_rendered_messages(trace ?? [])
  $: task_name = task?.name ?? ""
</script>

<div
  class="flex flex-col gap-6 w-full"
  data-testid="conversation-view"
  aria-label={task_name ? `Conversation for ${task_name}` : "Conversation"}
>
  {#each messages as message (message.key)}
    <MessageBlock
      role={message.role}
      content={message.content}
      reasoning_content={message.reasoning_content}
      tool_messages={message.tool_messages}
    />
  {/each}
</div>

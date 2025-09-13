<script lang="ts">
  import type { Trace, TraceMessage, ToolCallMessageParam } from "$lib/types"
  import Output from "../../../routes/(app)/run/output.svelte"
  import ToolCall from "./tool_call.svelte"

  export let trace: Trace

  // Track collapsed state for each message
  let collapsedStates: boolean[] = trace.map(() => true)

  function toggleCollapsed(index: number) {
    collapsedStates[index] = !collapsedStates[index]
    collapsedStates = [...collapsedStates] // Trigger reactivity
  }

  function getRoleDisplayName(role: string): string {
    return (
      {
        system: "System",
        user: "User",
        assistant: "Assistant",
        tool: "Tool",
        function: "Function",
        developer: "Developer",
      }[role] || role
    )
  }

  function getMessagePreview(message: TraceMessage): string {
    let content = content_from_message(message)
    let truncated_content = content
    // Truncate to keep DOM reasonable for unexpanded messages. The CSS separately truncates and adds ellipsis
    if (content && content.length > 200) {
      truncated_content = content.slice(0, 200)
    }
    let tool_calls = tool_calls_from_message(message)
    let reasoning_content = reasoning_content_from_message(message)

    // Tool result
    if (message.role === "tool" && content) {
      return "Tool result: " + truncated_content
    }

    // Mixed content
    let content_types = []
    if (tool_calls) {
      content_types.push("tool calls")
    }
    if (content) {
      content_types.push("message")
    }
    if (reasoning_content) {
      content_types.push("reasoning")
    }
    if (content_types.length > 1) {
      return "Multi-content: " + content_types.join(", ")
    }

    // Typical content message - just show the content
    if (truncated_content) {
      return truncated_content
    }

    // Tool calls - show the number of tool calls
    if (tool_calls && tool_calls.length > 0) {
      if (tool_calls.length === 1) {
        return `Requested tool call: ${tool_calls[0].function.name}`
      }
      return `Requested ${tool_calls.length} tool calls`
    }

    // Fallback
    return "Unrenderable message"
  }

  function tool_calls_from_message(
    message: TraceMessage,
  ): ToolCallMessageParam[] | undefined {
    if (
      "tool_calls" in message &&
      message.tool_calls &&
      message.tool_calls.length > 0
    ) {
      return message.tool_calls
    }
    return undefined
  }

  function content_from_message(message: TraceMessage) {
    if (
      "content" in message &&
      message.content &&
      typeof message.content === "string"
    ) {
      return message.content
    }
    return undefined
  }

  function origin_tool_call_by_id(tool_call_id: string) {
    for (const message of trace) {
      const tool_calls = tool_calls_from_message(message)
      if (tool_calls) {
        for (const tool_call of tool_calls) {
          if (tool_call.id === tool_call_id) {
            return tool_call
          }
        }
      }
    }
    return undefined
  }

  function reasoning_content_from_message(
    message: TraceMessage,
  ): string | undefined {
    if ("reasoning_content" in message && message.reasoning_content) {
      return message.reasoning_content
    }
    return undefined
  }
</script>

<div class="flex flex-col gap-3 w-full">
  {#each trace as message, index}
    <!-- Message Bubble -->
    <div class="">
      <div class="bg-base-200 rounded-lg p-3">
        <div
          class="flex items-center justify-between cursor-pointer"
          role="presentation"
          on:click={() => toggleCollapsed(index)}
        >
          <span class="font-medium text-xs min-w-[80px] text-gray-500 uppercase"
            >{getRoleDisplayName(message.role)}</span
          >
          <!-- Collapsed Preview -->
          <div
            class="px-2 text-sm text-gray-600 overflow-hidden text-ellipsis whitespace-nowrap grow {collapsedStates[
              index
            ]
              ? ''
              : 'hidden'}"
          >
            {getMessagePreview(message)}
          </div>
          <span class="text-gray-500 text-xs">
            {collapsedStates[index] ? "▼" : "▲"}
          </span>
        </div>

        {#if !collapsedStates[index]}
          {@const tool_calls = tool_calls_from_message(message)}
          {@const content = content_from_message(message)}
          {@const reasoning_content = reasoning_content_from_message(message)}
          <!-- Expanded View -->
          <div class="mt-3 flex flex-col gap-3">
            {#if tool_calls}
              <div>
                <div class="text-xs text-gray-500 font-bold mb-1">
                  Requested Tool Calls
                </div>
                <div class="flex flex-col gap-2">
                  {#each tool_calls as tool_call, index}
                    <ToolCall
                      {tool_call}
                      nameTag={tool_calls.length > 1
                        ? `Tool Call #${index + 1}`
                        : "Tool Call"}
                    />
                  {/each}
                </div>
              </div>
            {/if}
            {#if reasoning_content}
              <div>
                <div class="text-xs text-gray-500 font-bold mb-1">
                  Reasoning
                </div>
                <Output raw_output={reasoning_content} no_padding={true} />
              </div>
            {/if}

            <!-- Message content cases -->
            {#if content && message.role === "tool"}
              {@const origin_tool_call = origin_tool_call_by_id(
                message.tool_call_id,
              )}
              {#if origin_tool_call}
                <div>
                  <div class="text-xs text-gray-500 font-bold mb-1">
                    Invoked Tool Call
                  </div>
                  <ToolCall tool_call={origin_tool_call} />
                </div>
              {/if}
              <div>
                <div class="text-xs text-gray-500 font-bold mb-1">
                  Tool Result
                </div>
                <Output raw_output={content} no_padding={true} />
              </div>
            {:else if content}
              <div>
                <!-- Header logic: skip if only a message, just for a cleaner ui -->
                {#if tool_calls || reasoning_content}
                  <div class="text-xs text-gray-500 font-bold mb-1">
                    Content
                  </div>
                {/if}
                <Output raw_output={content} no_padding={true} />
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  {/each}
</div>

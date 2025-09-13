<script lang="ts">
  import type { Trace, TraceMessage } from "$lib/types"
  import Output from "../../../routes/(app)/run/output.svelte"

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
    let tool_calls = tool_calls_from_message(message)

    // Tool result
    if (message.role === "tool" && content) {
      return "Tool result: " + content
    }

    // Mixed content
    let content_types = []
    if (tool_calls) {
      content_types.push("tool calls")
    }
    if (content) {
      content_types.push("message")
    }
    if (content_types.length > 1) {
      return "Multiple content types: " + content_types.join(", ")
    }

    // Typical content message - just show the content
    if (content) {
      return content
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

  function tool_calls_from_message(message: TraceMessage) {
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
          <!-- Expanded View -->
          {#if tool_calls}
            <div class="mt-3 font-light">
              <div class="text-xs text-gray-500 font-bold">Tool Calls</div>
              <ol class="list-decimal list-inside font-light text-sm">
                {#each tool_calls as tool_call}
                  <li>
                    <span class="text-sm">
                      {tool_call.function.name}:
                    </span>
                    <span class="text-sm font-mono"
                      >{tool_call.function.arguments}</span
                    >
                  </li>
                {/each}
              </ol>
            </div>
          {/if}
          <!-- TODO Reasoning content -->
          {#if content}
            <div class="mt-4">
              {#if tool_calls}
                <!-- Only show header if other content is present -->
                <div class="text-xs text-gray-500 font-bold mt-2">
                  Message Content
                </div>
              {/if}
              <Output raw_output={content} no_padding={true} />
            </div>
          {/if}
        {/if}
      </div>
    </div>
  {/each}
</div>

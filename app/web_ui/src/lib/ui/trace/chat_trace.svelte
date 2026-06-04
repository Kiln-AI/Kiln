<script lang="ts">
  import type { Trace, TraceMessage, ToolCallMessageParam } from "$lib/types"
  import Output from "$lib/ui/output.svelte"
  import ChatMarkdown from "$lib/ui/chat/chat_markdown.svelte"
  import ArrowRightUpIcon from "../icons/arrow_right_up_icon.svelte"
  import ChatMessageActions from "./chat_message_actions.svelte"
  import ToolCall from "./tool_call.svelte"
  import ToolMessagesDialog from "./tool_messages_dialog.svelte"
  import UsageInfoDialog from "./usage_info_dialog.svelte"

  export let trace: Trace
  export let project_id: string | undefined = undefined
  // Positional map from trace index to a TaskRun id for that user turn.
  export let forkable_run_ids: (string | null)[] | undefined = undefined
  // When set, messages at trace indices >= this value are hidden.
  export let truncate_at_trace_index: number | null = null
  // Invoked when the user clicks a fork affordance on a user block.
  export let on_fork:
    | ((run_id: string, trace_index: number) => void)
    | undefined = undefined
  // Show the per-message usage info button.
  export let show_per_message_usage: boolean = false

  let thinkingExpanded: Record<number, boolean> = {}
  // Keyed by `${trace_index}-${tool_call_index}` so each tool call within an
  // assistant message expands independently.
  let toolCallExpanded: Record<string, boolean> = {}
  let tool_messages_dialog: ToolMessagesDialog | null = null
  let usage_info_dialog: UsageInfoDialog | null = null

  // Build a map: tool_call_id -> tool message so we can nest tool results
  // under the assistant turn that requested them.
  $: tool_results_by_call_id = (() => {
    const m = new Map<string, { message: TraceMessage; trace_index: number }>()
    trace.forEach((message, idx) => {
      if (
        message.role === "tool" &&
        "tool_call_id" in message &&
        typeof message.tool_call_id === "string"
      ) {
        m.set(message.tool_call_id, { message, trace_index: idx })
      }
    })
    return m
  })()

  function content_from_message(message: TraceMessage): string | undefined {
    if (
      "content" in message &&
      message.content &&
      typeof message.content === "string"
    ) {
      if (message.role === "tool") {
        try {
          const parsed = JSON.parse(message.content)
          if (parsed && typeof parsed === "object" && "output" in parsed) {
            return typeof parsed.output === "string"
              ? parsed.output
              : JSON.stringify(parsed.output, null, 2)
          }
          if (
            parsed &&
            typeof parsed === "object" &&
            parsed.isError === true &&
            "error" in parsed
          ) {
            return typeof parsed.error === "string"
              ? parsed.error
              : JSON.stringify(parsed.error, null, 2)
          }
        } catch (_) {
          // Not JSON, return as-is.
        }
      }
      return message.content
    }
    return undefined
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

  function reasoning_from_message(message: TraceMessage): string | undefined {
    if (
      "reasoning_content" in message &&
      message.reasoning_content &&
      typeof message.reasoning_content === "string"
    ) {
      return message.reasoning_content
    }
    return undefined
  }

  function is_tool_error(message: TraceMessage): boolean {
    if (message.role !== "tool") return false
    if ("is_error" in message && message.is_error) return true
    if ("content" in message && typeof message.content === "string") {
      try {
        const parsed = JSON.parse(message.content)
        if (parsed && typeof parsed === "object" && parsed.isError === true) {
          return true
        }
      } catch (_) {
        // Not JSON.
      }
    }
    return false
  }

  function kiln_task_tool_data_from_message(message: TraceMessage): {
    project_id: string
    tool_id: string
    task_id: string
    run_id: string
  } | null {
    if (
      "kiln_task_tool_data" in message &&
      message.kiln_task_tool_data &&
      typeof message.kiln_task_tool_data === "string"
    ) {
      const [p_id, tool_id, task_id, run_id] =
        message.kiln_task_tool_data.split(":::")
      if (p_id && tool_id && task_id && run_id) {
        return { project_id: p_id, tool_id, task_id, run_id }
      }
    }
    return null
  }

  function message_usage(message: TraceMessage) {
    if ("usage" in message && message.usage) return message.usage
    return null
  }

  function message_latency_ms(message: TraceMessage): number | null {
    if (
      "latency_ms" in message &&
      typeof message.latency_ms === "number" &&
      message.latency_ms > 0
    ) {
      return message.latency_ms
    }
    return null
  }

  function has_usage_info(message: TraceMessage): boolean {
    return (
      message_usage(message) !== null || message_latency_ms(message) !== null
    )
  }

  function open_usage_dialog(message: TraceMessage) {
    usage_info_dialog?.show({
      usage: message_usage(message),
      latency_ms: message_latency_ms(message),
    })
  }
</script>

<div class="flex flex-col gap-3 w-full">
  {#each trace as message, index}
    {#if (truncate_at_trace_index === null || index < truncate_at_trace_index) && message.role !== "tool" && message.role !== "system" && message.role !== "developer"}
      {@const fork_run_id = forkable_run_ids?.[index] ?? null}
      {@const show_fork = !!(message.role === "user" && fork_run_id && on_fork)}
      {@const show_info = show_per_message_usage && has_usage_info(message)}
      {@const content = content_from_message(message)}
      {@const reasoning = reasoning_from_message(message)}
      {@const tool_calls = tool_calls_from_message(message)}
      {@const has_reasoning_bubble = !!reasoning}
      {@const has_content_bubble = !!content}
      {@const has_tc_bubble = !!(tool_calls && tool_calls.length > 0)}
      {@const empty_assistant =
        !has_reasoning_bubble &&
        !has_content_bubble &&
        !has_tc_bubble &&
        message.role !== "user"}

      {#if message.role === "user"}
        <!-- `group` so the actions row below reveals on hover/focus. -->
        <div class="group flex flex-col items-end" data-testid="chat-msg-user">
          <div class="rounded-xl bg-primary/10 px-4 py-3 max-w-[70%] text-sm">
            {#if content}
              <ChatMarkdown text={content} />
            {:else}
              <span class="text-gray-400 italic">(empty message)</span>
            {/if}
          </div>
          {#if show_info || show_fork}
            <ChatMessageActions
              align="end"
              show_usage={show_info}
              show_fork={!!show_fork}
              on_usage={() => open_usage_dialog(message)}
              on_fork={() => {
                if (fork_run_id) on_fork?.(fork_run_id, index)
              }}
            />
          {/if}
        </div>
      {:else}
        <!-- One group per assistant turn: all of its bubbles share a single
             hover-revealed actions row rendered below them. -->
        <div
          class="group flex flex-col items-start"
          data-testid="chat-msg-assistant-turn"
        >
          <div class="flex w-full flex-col gap-3">
            {#if has_reasoning_bubble}
              <!-- Assistant reasoning bubble. Collapsed by default; toggling
                   reveals the model's thinking. -->
              <div
                class="flex flex-col items-start"
                data-testid="chat-msg-assistant"
              >
                <!-- Whole-bubble click expands when collapsed. The inner toggle
                     button uses |stopPropagation so it still owns collapsing
                     (and the container handler never accidentally re-expands). -->
                <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                <div
                  class="rounded-xl bg-base-200 px-4 py-3 w-[70%] text-sm flex flex-col gap-2"
                  class:cursor-pointer={!thinkingExpanded[index]}
                  on:click={() => {
                    if (!thinkingExpanded[index]) thinkingExpanded[index] = true
                  }}
                >
                  <div data-testid="chat-msg-thinking">
                    <button
                      type="button"
                      class="flex w-full items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 cursor-pointer"
                      on:click|stopPropagation={() =>
                        (thinkingExpanded[index] = !thinkingExpanded[index])}
                      aria-expanded={!!thinkingExpanded[index]}
                    >
                      <span class="text-gray-400" aria-hidden="true">
                        {thinkingExpanded[index] ? "▼" : "▶"}
                      </span>
                      <span class="font-medium">Thinking</span>
                    </button>
                    {#if thinkingExpanded[index]}
                      <div class="mt-2">
                        <ChatMarkdown text={reasoning} />
                      </div>
                    {/if}
                  </div>
                </div>
              </div>
            {/if}

            {#if has_content_bubble}
              <!-- Assistant content bubble. -->
              <div
                class="flex flex-col items-start"
                data-testid="chat-msg-assistant"
              >
                <div
                  class="rounded-xl bg-base-200 px-4 py-3 w-[70%] text-sm flex flex-col gap-2"
                >
                  <div data-testid="chat-msg-content">
                    <ChatMarkdown text={content} />
                  </div>
                </div>
              </div>
            {/if}

            {#if has_tc_bubble && tool_calls}
              {#each tool_calls as tool_call, tcIdx}
                <!-- One bubble per tool call. -->
                {@const tc_key = `${index}-${tcIdx}`}
                {@const result =
                  tool_results_by_call_id.get(tool_call.id) ?? null}
                {@const result_content = result
                  ? content_from_message(result.message)
                  : undefined}
                {@const kiln_data = result
                  ? kiln_task_tool_data_from_message(result.message)
                  : null}
                {@const tool_error = result
                  ? is_tool_error(result.message)
                  : false}
                <div
                  class="flex flex-col items-start"
                  data-testid="chat-msg-assistant"
                >
                  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                  <div
                    class="rounded-xl bg-base-200 px-4 py-3 w-[70%] text-sm flex flex-col gap-2"
                    class:cursor-pointer={!toolCallExpanded[tc_key]}
                    on:click={() => {
                      if (!toolCallExpanded[tc_key])
                        toolCallExpanded[tc_key] = true
                    }}
                  >
                    <div data-testid="chat-msg-toolcall">
                      <button
                        type="button"
                        class="flex w-full items-center gap-1.5 text-xs text-gray-600 hover:text-gray-900 cursor-pointer"
                        on:click|stopPropagation={() =>
                          (toolCallExpanded[tc_key] =
                            !toolCallExpanded[tc_key])}
                        aria-expanded={!!toolCallExpanded[tc_key]}
                      >
                        <span class="text-gray-400" aria-hidden="true">
                          {toolCallExpanded[tc_key] ? "▼" : "▶"}
                        </span>
                        <span class="font-medium">
                          Toolcall: <span class="font-mono"
                            >{tool_call.function.name}</span
                          >
                        </span>
                      </button>
                      {#if toolCallExpanded[tc_key]}
                        <div
                          class="mt-3 flex flex-col gap-3"
                          data-testid="chat-tool-call"
                        >
                          <div>
                            <div class="text-xs text-gray-500 font-bold mb-1">
                              Invoked Tool Call
                            </div>
                            <ToolCall
                              {tool_call}
                              {project_id}
                              persistent_tool_id={kiln_data?.tool_id}
                            />
                          </div>
                          {#if result_content !== undefined}
                            <div>
                              <div
                                class="text-xs font-bold mb-1 {tool_error
                                  ? 'text-error'
                                  : 'text-gray-500'}"
                              >
                                {tool_error ? "Tool Error" : "Tool Result"}
                              </div>
                              <div
                                class={tool_error
                                  ? "border border-error/20 rounded-lg p-2"
                                  : ""}
                              >
                                <Output
                                  raw_output={result_content}
                                  no_padding={true}
                                />
                              </div>
                            </div>
                          {:else if result === null}
                            <div class="text-xs text-gray-400 italic">
                              No tool result recorded.
                            </div>
                          {/if}
                          {#if kiln_data}
                            <div>
                              <button
                                class="link text-xs text-gray-500"
                                on:click={() => {
                                  tool_messages_dialog?.show(kiln_data)
                                }}
                              >
                                <div class="flex flex-row items-center gap-1">
                                  <span>Subtask Message Trace</span>
                                  <div class="w-4 h-4">
                                    <ArrowRightUpIcon />
                                  </div>
                                </div>
                              </button>
                            </div>
                          {/if}
                        </div>
                      {/if}
                    </div>
                  </div>
                </div>
              {/each}
            {/if}

            {#if empty_assistant}
              <div
                class="flex flex-col items-start"
                data-testid="chat-msg-assistant"
              >
                <div
                  class="rounded-xl bg-base-200 px-4 py-3 w-[70%] text-sm text-gray-400 italic"
                >
                  (empty message)
                </div>
              </div>
            {/if}
          </div>
          {#if show_info}
            <!-- Constrain to the bubble width so the right-aligned action sits
                 at the bubble's right edge, not the far column edge. -->
            <div class="w-[70%]">
              <ChatMessageActions
                align="end"
                show_usage={true}
                show_fork={false}
                on_usage={() => open_usage_dialog(message)}
              />
            </div>
          {/if}
        </div>
      {/if}
    {/if}
  {/each}
</div>

<ToolMessagesDialog bind:this={tool_messages_dialog} {project_id} />
<UsageInfoDialog bind:this={usage_info_dialog} />

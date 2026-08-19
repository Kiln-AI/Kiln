<script lang="ts">
  import { tick } from "svelte"
  import type { Trace, TraceMessage, ToolCallMessageParam } from "$lib/types"
  // Structured content renders through Output (pretty-print + syntax highlight)
  // rather than markdown, which collapses 2-space-indented JSON into a run-on
  // paragraph. Output owns the rule so every surface routes content the same.
  import Output, { is_non_string_json } from "$lib/ui/output.svelte"
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
  // Optional citation highlight: a resolved span pointing at one block of one
  // message. When set, that node renders the span wrapped in <mark>, the
  // component scrolls to it, and any collapsed thinking/tool bubble it lives in
  // auto-expands. When null (the default — e.g. the dataset run page), the
  // render is unchanged. `start`/`end` index the block's RAW text, matching the
  // flattener the citation resolved against; content and reasoning nodes render
  // that raw text (markdown is dropped for the marked node only) so the offsets
  // line up, while tool blocks just expand + scroll to the cited bubble.
  export let highlight: {
    trace_index: number
    kind: "content" | "reasoning" | "tool_calls" | "tool_result"
    start: number
    end: number
  } | null = null

  let root_el: HTMLElement | null = null

  // Split a block's raw text around the highlight span for <mark> rendering.
  function highlight_segments(
    text: string,
    h: { start: number; end: number },
  ): { before: string; mark: string; after: string } {
    const start = Math.max(0, Math.min(h.start, text.length))
    const end = Math.max(start, Math.min(h.end, text.length))
    return {
      before: text.slice(0, start),
      mark: text.slice(start, end),
      after: text.slice(end),
    }
  }

  // A tool-RESULT citation's trace_index is the tool message; find the
  // assistant turn + tool-call slot that renders it, so we can expand it.
  function owner_of_tool_result(
    tool_index: number,
  ): { index: number; tcIdx: number } | null {
    const m = trace[tool_index]
    const tid =
      m && "tool_call_id" in m && typeof m.tool_call_id === "string"
        ? m.tool_call_id
        : null
    if (!tid) return null
    for (let i = 0; i < trace.length; i++) {
      const tcs = tool_calls_from_message(trace[i])
      if (!tcs) continue
      for (let tcIdx = 0; tcIdx < tcs.length; tcIdx++) {
        if (tcs[tcIdx].id === tid) return { index: i, tcIdx }
      }
    }
    return null
  }

  // Expand whatever collapsible bubble the highlight lives in, so the cited
  // moment is visible before we scroll to it.
  $: apply_highlight_expansion(highlight)
  function apply_highlight_expansion(h: typeof highlight): void {
    if (!h) return
    if (h.kind === "reasoning") {
      thinkingExpanded[h.trace_index] = true
      thinkingExpanded = thinkingExpanded
    } else if (h.kind === "tool_calls") {
      const tcs = tool_calls_from_message(trace[h.trace_index]) ?? []
      tcs.forEach(
        (_, tcIdx) => (toolCallExpanded[`${h.trace_index}-${tcIdx}`] = true),
      )
      toolCallExpanded = toolCallExpanded
    } else if (h.kind === "tool_result") {
      const owner = owner_of_tool_result(h.trace_index)
      if (owner) toolCallExpanded[`${owner.index}-${owner.tcIdx}`] = true
      toolCallExpanded = toolCallExpanded
    }
  }

  // Bring the marked node (or the expanded target bubble) into view whenever
  // the highlight changes — the modal reuses one component across citations.
  $: scroll_to_highlight(highlight)
  async function scroll_to_highlight(h: typeof highlight): Promise<void> {
    if (!h || typeof document === "undefined") return
    await tick()
    const el = root_el?.querySelector("[data-highlight-target]")
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "center", behavior: "smooth" })
    }
  }

  // The assistant turn + tool-call slot a tool-result highlight targets.
  $: tool_result_owner =
    highlight && highlight.kind === "tool_result"
      ? owner_of_tool_result(highlight.trace_index)
      : null

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

<div class="flex flex-col gap-3 w-full" bind:this={root_el}>
  {#each trace as message, index}
    {#if (truncate_at_trace_index === null || index < truncate_at_trace_index) && message.role !== "tool" && message.role !== "system" && message.role !== "developer"}
      {@const fork_run_id = forkable_run_ids?.[index] ?? null}
      {@const show_fork = !!(message.role !== "user" && fork_run_id && on_fork)}
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
              {#if is_non_string_json(content)}
                <!-- Transparent so the user turn keeps its tint. Markdown code
                     blocks already render on the tint here, so a JSON panel on
                     it matches the bubble's existing visual language. -->
                <Output
                  raw_output={content}
                  no_padding={true}
                  background_color="transparent"
                />
              {:else}
                <ChatMarkdown text={content} />
              {/if}
            {:else}
              <span class="text-gray-400 italic">(empty message)</span>
            {/if}
          </div>
          {#if show_info}
            <ChatMessageActions
              align="end"
              show_usage={show_info}
              show_fork={false}
              on_usage={() => open_usage_dialog(message)}
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
                        {#if highlight && highlight.kind === "reasoning" && highlight.trace_index === index && reasoning}
                          {@const seg = highlight_segments(
                            reasoning,
                            highlight,
                          )}
                          <!-- Marked node renders as plain text: the offsets
                               index the raw reasoning, not rendered markdown. -->
                          <div class="whitespace-pre-wrap">
                            {seg.before}<mark
                              data-highlight-target
                              class="bg-warning/40 rounded px-0.5"
                              >{seg.mark}</mark
                            >{seg.after}
                          </div>
                        {:else if reasoning && is_non_string_json(reasoning)}
                          <!-- The legacy trace view renders reasoning through
                               Output, so structured reasoning read as a
                               collapsed paragraph only in the chat view. -->
                          <Output raw_output={reasoning} no_padding={true} />
                        {:else}
                          <ChatMarkdown text={reasoning} />
                        {/if}
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
                    {#if highlight && highlight.kind === "content" && highlight.trace_index === index && content}
                      {@const seg = highlight_segments(content, highlight)}
                      <!-- Marked node renders as plain text: the offsets index
                           the raw content, not rendered markdown. -->
                      <div class="whitespace-pre-wrap">
                        {seg.before}<mark
                          data-highlight-target
                          class="bg-warning/40 rounded px-0.5">{seg.mark}</mark
                        >{seg.after}
                      </div>
                    {:else if content && is_non_string_json(content)}
                      <Output raw_output={content} no_padding={true} />
                    {:else}
                      <ChatMarkdown text={content} />
                    {/if}
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
                <!-- A tool citation lands on the whole bubble (its call and
                     result render via dedicated components, not plain text):
                     mark the bubble as the scroll target and let the reactive
                     expansion open it. -->
                {@const is_tc_target = !!(
                  highlight &&
                  ((highlight.kind === "tool_calls" &&
                    highlight.trace_index === index &&
                    tcIdx === 0) ||
                    (highlight.kind === "tool_result" &&
                      tool_result_owner &&
                      tool_result_owner.index === index &&
                      tool_result_owner.tcIdx === tcIdx))
                )}
                <div
                  class="flex flex-col items-start"
                  data-testid="chat-msg-assistant"
                >
                  <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
                  <div
                    class="rounded-xl bg-base-200 px-4 py-3 w-[70%] text-sm flex flex-col gap-2"
                    data-highlight-target={is_tc_target ? "" : undefined}
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
          {#if show_info || show_fork}
            <!-- Constrain to the bubble width so the right-aligned actions sit
                 at the bubble's right edge, not the far column edge. -->
            <div class="w-[70%]">
              <ChatMessageActions
                align="end"
                show_usage={show_info}
                show_fork={!!show_fork}
                on_usage={() => open_usage_dialog(message)}
                on_fork={() => {
                  if (fork_run_id) on_fork?.(fork_run_id, index)
                }}
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

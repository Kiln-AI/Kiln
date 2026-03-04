<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { current_task, current_project } from "$lib/stores"
  import { base_url } from "$lib/api_client"
  import { createKilnError } from "$lib/utils/error_handlers"
  import { KilnError } from "$lib/utils/error_handlers"
  import { readUIMessageStream, type UIMessage } from "ai"
  import { sseToUIMessageChunkStream } from "$lib/chat/sse_to_ui_stream"

  type DisplayPart =
    | { type: "text"; text: string }
    | { type: "reasoning"; text: string }
    | {
        type: "tool"
        toolName: string
        input: unknown
        output?: unknown
        pending?: boolean
      }

  type DisplayMessage = {
    id: string
    role: "user" | "assistant"
    parts: DisplayPart[]
    isStreaming?: boolean
  }

  let chat_error: KilnError | null = null
  let streaming = false
  let input_text = ""
  let messages: DisplayMessage[] = []
  let messages_container: HTMLElement | null = null
  let abort_controller: AbortController | null = null

  $: project_id = $current_project?.id ?? ""
  $: task_id = $current_task?.id ?? ""
  $: subtitle = $current_task ? "Task: " + $current_task.name : ""
  $: can_send = Boolean(
    project_id && task_id && !streaming && input_text.trim(),
  )

  function has_tool_input(part: DisplayPart): boolean {
    if (part.type !== "tool") return false
    if (part.input == null) return false
    return Object.keys(part.input as object).length > 0
  }

  function is_tool_part(part: { type: string }): boolean {
    return (
      part.type === "dynamic-tool" ||
      part.type === "tool-call" ||
      part.type === "tool-result" ||
      part.type.startsWith("tool-")
    )
  }

  function tool_name_from_part(part: {
    type: string
    toolName?: string
  }): string {
    if (part.toolName) return part.toolName
    if (part.type.startsWith("tool-")) return part.type.slice(5)
    return "unknown"
  }

  function parts_from_ui_message(msg: UIMessage): DisplayPart[] {
    const parts: DisplayPart[] = []
    for (const part of msg.parts) {
      if (part.type === "text") {
        parts.push({ type: "text", text: part.text })
      } else if (part.type === "reasoning") {
        parts.push({ type: "reasoning", text: part.text })
      } else if (is_tool_part(part)) {
        const toolPart = part as {
          type: string
          toolName?: string
          input?: unknown
          output?: unknown
          state?: string
        }
        const toolName = tool_name_from_part(toolPart)
        const hasOutput = toolPart.output !== undefined
        parts.push({
          type: "tool",
          toolName,
          input: toolPart.input ?? {},
          output: toolPart.output,
          pending: !hasOutput,
        })
      }
    }
    return parts
  }

  async function send_message(event?: SubmitEvent) {
    event?.preventDefault()
    const text = input_text.trim()
    if (!text || !project_id || !task_id) return

    try {
      streaming = true
      chat_error = null
      abort_controller = new AbortController()
      messages = [
        ...messages,
        { id: crypto.randomUUID(), role: "user", parts: [{ type: "text", text }] },
      ]
      input_text = ""

      const res = await fetch(
        `${base_url}/api/projects/${project_id}/tasks/${task_id}/chat/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: text }),
          signal: abort_controller.signal,
        },
      )
      if (!res.ok) {
        const errText = await res.text()
        throw new Error(errText || `HTTP ${res.status}`)
      }
      if (!res.body) throw new Error("No response body")

      const chunkStream = sseToUIMessageChunkStream(res.body)
      const uiMessageStream = readUIMessageStream({ stream: chunkStream })
      let lastMessage: UIMessage | null = null

      messages = [
        ...messages,
        { id: "streaming", role: "assistant", parts: [], isStreaming: true },
      ]

      for await (const uiMessage of uiMessageStream) {
        lastMessage = uiMessage
        messages = [
          ...messages.slice(0, -1),
          {
            id: uiMessage.id ?? "streaming",
            role: "assistant",
            parts: parts_from_ui_message(uiMessage),
            isStreaming: true,
          },
        ]
      }

      messages = [
        ...messages.slice(0, -1),
        {
          id: lastMessage?.id ?? crypto.randomUUID(),
          role: "assistant",
          parts: lastMessage ? parts_from_ui_message(lastMessage) : [],
          isStreaming: false,
        },
      ]
    } catch (e) {
      if ((e as Error).name === "AbortError") return
      chat_error = createKilnError(e)
      if (
        messages[messages.length - 1]?.role === "assistant" &&
        messages[messages.length - 1]?.parts.length === 0
      ) {
        messages = messages.slice(0, -1)
      }
    } finally {
      streaming = false
      abort_controller = null
      setTimeout(() => {
        messages_container?.scrollTo({
          top: messages_container.scrollHeight,
          behavior: "smooth",
        })
      }, 0)
    }
  }

  function stop_streaming() {
    abort_controller?.abort()
  }
</script>

<div class="max-w-[1400px] flex flex-col h-[calc(100vh-12rem)]">
  <AppPage title="Chat (AI SDK)" bind:subtitle>
    <div class="flex flex-col gap-4 flex-1 min-h-0">
      {#if !$current_task}
        <p class="text-base-content/70">
          Select a project and task from the sidebar to start chatting.
        </p>
      {:else}
        <div class="flex flex-col gap-4 max-w-3xl flex-1 min-h-0">
          <div
            bind:this={messages_container}
            class="flex-1 border border-base-300 rounded-lg p-4 overflow-y-auto bg-base-200/50 min-h-[200px]"
          >
            {#if messages.length === 0}
              <p class="text-base-content/60 text-sm">
                Type a message below and press Send. Responses stream in real
                time.
              </p>
            {:else}
              <div class="flex flex-col gap-4">
                {#each messages as msg (msg.id)}
                  <div
                    class="flex flex-col gap-1 {msg.role === 'user'
                      ? 'items-end'
                      : 'items-start'}"
                  >
                    <span
                      class="text-xs font-medium text-base-content/60 {msg.role ===
                      'user'
                        ? 'mr-2'
                        : 'ml-2'}"
                    >
                      {msg.role === "user" ? "You" : "Assistant"}
                    </span>
                    <div
                      class="max-w-[85%] rounded-lg px-4 py-2 {msg.role ===
                      'user'
                        ? 'bg-primary text-primary-content'
                        : 'bg-base-300'}"
                    >
                      {#each msg.parts as part}
                        {#if part.type === "text"}
                          <div class="whitespace-pre-wrap break-words">
                            {part.text || (msg.isStreaming ? "…" : "")}
                          </div>
                        {:else if part.type === "reasoning"}
                          <details class="mb-2">
                            <summary
                              class="text-xs text-base-content/60 cursor-pointer"
                            >
                              Reasoning
                            </summary>
                            <div
                              class="mt-1 text-sm text-base-content/70 whitespace-pre-wrap break-words"
                            >
                              {part.text}
                            </div>
                          </details>
                        {:else if part.type === "tool"}
                          <div
                            class="text-xs font-mono bg-base-200 rounded px-2 py-1.5 mb-2"
                          >
                            <span class="font-semibold text-primary"
                              >{part.toolName}</span
                            >
                            {#if has_tool_input(part)}
                              <span class="text-base-content/70">
                                ({JSON.stringify(part.input)})</span
                              >
                            {/if}
                            {#if part.pending}
                              <span
                                class="text-base-content/50 italic mt-1 inline-flex items-center gap-1"
                              >
                                Calling…
                                <span
                                  class="inline-block w-2 h-3 bg-current animate-pulse"
                                />
                              </span>
                            {:else if part.output !== undefined}
                              <span class="text-success block mt-1">
                                → {typeof part.output === "object"
                                  ? JSON.stringify(part.output)
                                  : String(part.output)}</span
                              >
                            {/if}
                          </div>
                        {/if}
                      {/each}
                      {#if msg.isStreaming && msg.parts.length === 0}
                        <span class="text-base-content/60">…</span>
                      {/if}
                      {#if msg.isStreaming}
                        <span
                          class="inline-block w-2 h-4 bg-current animate-pulse ml-0.5"
                        />
                      {/if}
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <form on:submit={send_message} class="flex flex-col gap-2">
            {#if chat_error}
              <div class="text-sm text-error">
                {#each chat_error.getErrorMessages() as line}
                  <div>{line}</div>
                {/each}
              </div>
            {/if}
            <div class="flex gap-2">
              <textarea
                class="textarea textarea-bordered flex-1 min-h-[80px] resize-none"
                placeholder="Type your message..."
                bind:value={input_text}
                disabled={streaming}
                rows="2"
              />
              <div class="flex flex-col gap-1">
                {#if streaming}
                  <button
                    type="button"
                    class="btn btn-error btn-sm"
                    on:click={stop_streaming}
                  >
                    Stop
                  </button>
                {:else}
                  <button
                    type="submit"
                    class="btn btn-primary"
                    disabled={!can_send}
                  >
                    Send
                  </button>
                {/if}
              </div>
            </div>
          </form>
        </div>
      {/if}
    </div>
  </AppPage>
</div>

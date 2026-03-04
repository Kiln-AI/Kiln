<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { current_task, current_project } from "$lib/stores"
  import { base_url } from "$lib/api_client"
  import { createKilnError } from "$lib/utils/error_handlers"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { KilnError } from "$lib/utils/error_handlers"
  import RunInputForm from "../run/run_input_form.svelte"

  type ChatMessage = {
    role: "user" | "assistant"
    content: string
    isStreaming?: boolean
  }

  let chat_error: KilnError | null = null
  let streaming = false
  let input_form: RunInputForm
  let messages: ChatMessage[] = []
  let messages_container: HTMLElement | null = null

  $: project_id = $current_project?.id ?? ""
  $: task_id = $current_task?.id ?? ""
  $: input_schema = $current_task?.input_json_schema
  $: subtitle = $current_task ? "Task: " + $current_task.name : ""
  $: can_send = Boolean(project_id && task_id && !streaming && input_form)

  async function send_message() {
    if (!input_form) return

    const user_input =
      input_schema == null
        ? input_form.get_plaintext_input_data()
        : input_form.get_structured_input_data()
    const input_for_api = user_input
    const input_display =
      typeof input_for_api === "string"
        ? input_for_api
        : JSON.stringify(input_for_api)
    if (
      input_for_api == null ||
      (typeof input_for_api === "string" && !input_for_api.trim())
    ) {
      chat_error = createKilnError(new Error("Enter a message to send."))
      return
    }

    try {
      streaming = true
      chat_error = null
      messages = [...messages, { role: "user", content: input_display }]
      input_form.clear_input()

      const res = await fetch(
        `${base_url}/api/projects/${project_id}/tasks/${task_id}/chat/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: input_for_api }),
        },
      )
      if (!res.ok) {
        const errText = await res.text()
        throw new Error(errText || `HTTP ${res.status}`)
      }
      if (!res.body) throw new Error("No response body")

      let streamed_content = ""
      messages = [
        ...messages,
        {
          role: "assistant" as const,
          content: "",
          isStreaming: true,
        },
      ]

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6)
            if (data === "[DONE]") {
              messages = [
                ...messages.slice(0, -1),
                {
                  role: "assistant" as const,
                  content: streamed_content,
                  isStreaming: false,
                },
              ]
              break
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.type === "text-delta" && parsed.delta) {
                streamed_content += parsed.delta
                messages = [
                  ...messages.slice(0, -1),
                  {
                    role: "assistant" as const,
                    content: streamed_content,
                    isStreaming: true,
                  },
                ]
              } else if (parsed.type === "reasoning-delta" && parsed.delta) {
                streamed_content += parsed.delta
                messages = [
                  ...messages.slice(0, -1),
                  {
                    role: "assistant" as const,
                    content: streamed_content,
                    isStreaming: true,
                  },
                ]
              }
            } catch {
              // ignore parse errors for non-JSON lines
            }
          }
        }
      }
      messages = [
        ...messages.slice(0, -1),
        {
          role: "assistant" as const,
          content: streamed_content,
          isStreaming: false,
        },
      ]
    } catch (e) {
      chat_error = createKilnError(e)
      if (
        messages[messages.length - 1]?.role === "assistant" &&
        messages[messages.length - 1]?.content === ""
      ) {
        messages = messages.slice(0, -1)
      }
    } finally {
      streaming = false
      setTimeout(() => {
        messages_container?.scrollTo({
          top: messages_container.scrollHeight,
          behavior: "smooth",
        })
      }, 0)
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage title="Chat" bind:subtitle>
    <div class="flex flex-col gap-6">
      {#if !$current_task}
        <p class="text-base-content/70">
          Select a project and task from the sidebar to start chatting.
        </p>
      {:else}
        <div class="flex flex-col gap-4 max-w-3xl">
          <div class="text-xl font-bold">Messages</div>
          <div
            bind:this={messages_container}
            class="border border-base-300 rounded-lg p-4 min-h-[200px] max-h-[400px] overflow-y-auto bg-base-200/50"
          >
            {#if messages.length === 0}
              <p class="text-base-content/60 text-sm">
                Send a message to start the conversation. Responses stream in
                real time.
              </p>
            {:else}
              <div class="flex flex-col gap-4">
                {#each messages as msg, i (i)}
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
                      <div class="whitespace-pre-wrap break-words">
                        {msg.content || (msg.isStreaming ? "…" : "")}
                      </div>
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

          <div class="text-xl font-bold">Input</div>
          <FormContainer
            submit_label="Send"
            on:submit={send_message}
            bind:error={chat_error}
            submitting={streaming}
            primary={can_send}
            keyboard_submit={can_send}
          >
            <RunInputForm bind:input_schema bind:this={input_form} />
          </FormContainer>
        </div>
      {/if}
    </div>
  </AppPage>
</div>

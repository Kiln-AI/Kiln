// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import type { ChatMessage } from "$lib/chat/streaming_chat"

const ChatTranscript = (await import("./chat_transcript.svelte")).default

afterEach(() => {
  cleanup()
})

function toolPart(id: string, withOutput = true) {
  return {
    type: "tool-call_kiln_api" as const,
    toolCallId: id,
    toolName: "call_kiln_api",
    input: { method: "GET", url_path: `/api/thing/${id}` },
    ...(withOutput ? { output: "ok" } : {}),
  }
}

describe("chat_transcript", () => {
  it("renders user bubbles, assistant markdown and tool status lines", () => {
    const messages: ChatMessage[] = [
      { id: "u1", role: "user", content: "Begin work on: Eval sweep." },
      {
        id: "a1",
        role: "assistant",
        parts: [toolPart("tc1"), { type: "text", text: "All **done**." }],
      },
    ]
    const { container } = render(ChatTranscript, { props: { messages } })
    expect(container.textContent).toContain("Begin work on: Eval sweep.")
    expect(container.textContent).toContain("Fetched data")
    expect(container.textContent).toContain("(GET /api/thing/tc1)")
    // Markdown rendered (bold), not raw asterisks.
    expect(container.querySelector("strong")?.textContent).toBe("done")
  })

  it("compresses long step groups and expands on toggle", async () => {
    const messages: ChatMessage[] = [
      {
        id: "a1",
        role: "assistant",
        parts: [
          ...Array.from({ length: 7 }, (_, i) => toolPart(`tc${i}`)),
          { type: "text", text: "Summary." },
        ],
      },
    ]
    const onStepGroupToggle = vi.fn()
    const { container, getByRole } = render(ChatTranscript, {
      props: { messages, onStepGroupToggle },
    })
    // 7 steps, 5 visible → "… 2 more steps ▶".
    expect(container.textContent).toContain("… 2 more steps ▶")
    await fireEvent.click(getByRole("button", { name: "… 2 more steps ▶" }))
    expect(onStepGroupToggle).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain("7 steps ▼")
    expect(container.textContent).toContain("(GET /api/thing/tc0)")
  })

  it("renders a sub-agent report chip instead of a user bubble", () => {
    const messages: ChatMessage[] = [
      {
        id: "u1",
        role: "user",
        content: "report body",
        subagentReport: {
          id: "sa_1",
          agentType: "general",
          status: "completed",
          title: "Eval sweep",
        },
      },
    ]
    const { container } = render(ChatTranscript, { props: { messages } })
    expect(container.textContent).toContain("Sub-agent report")
    expect(container.textContent).toContain("Eval sweep")
    // Collapsed by default: the body only shows after expanding.
    expect(container.textContent).not.toContain("report body")
  })

  it("shows the error Retry button interactively but not in readOnly", async () => {
    const messages: ChatMessage[] = [
      { id: "e1", role: "error", content: "boom" },
    ]
    const onRetryLastRequest = vi.fn()
    const interactive = render(ChatTranscript, {
      props: { messages, onRetryLastRequest },
    })
    await fireEvent.click(interactive.getByRole("button", { name: "Retry" }))
    expect(onRetryLastRequest).toHaveBeenCalledTimes(1)
    cleanup()

    const readOnly = render(ChatTranscript, {
      props: { messages, readOnly: true },
    })
    expect(readOnly.container.textContent).toContain("boom")
    expect(readOnly.queryByRole("button", { name: "Retry" })).toBeNull()
  })

  it("hides empty assistant messages unless they are the live last turn", () => {
    const messages: ChatMessage[] = [
      { id: "u1", role: "user", content: "hi" },
      { id: "a1", role: "assistant", parts: [] },
    ]
    const idle = render(ChatTranscript, { props: { messages } })
    expect(idle.container.querySelectorAll("img").length).toBe(0)
    cleanup()

    // Live last turn: the streaming-cursor indicator (animated icon) shows.
    const live = render(ChatTranscript, {
      props: { messages, loading: true },
    })
    expect(live.container.querySelectorAll("img").length).toBeGreaterThan(0)
  })
})

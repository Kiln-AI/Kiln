// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import type { ChatMessage } from "$lib/chat/streaming_chat"
import type { ConversationItem } from "$lib/chat/conversation_store"

const SubagentTranscript = (await import("./subagent_transcript.svelte"))
  .default

afterEach(() => {
  cleanup()
})

function child(overrides: Partial<ConversationItem> = {}): ConversationItem {
  return {
    session_id: "cv_1",
    kind: "subagent",
    state: "running",
    name: "Eval sweep",
    agent_type: "general",
    parent_session_id: "trace:parent-1",
    auto_flag: false,
    rounds_used: 0,
    report_available: false,
    report_delivered: false,
    ...overrides,
  }
}

const kickoffMessage: ChatMessage = {
  id: "u1",
  role: "user",
  content: "Eval sweep — your assignment:\n\nDo the thing.",
}

describe("subagent_transcript working indicator", () => {
  it("shows the thinking indicator when running with an empty transcript", () => {
    const { container } = render(SubagentTranscript, {
      props: { child: child(), messages: [] },
    })
    const status = container.querySelector('[role="status"]')
    expect(status).not.toBeNull()
    expect(status?.textContent).toContain("Thinking")
  })

  it("shows the thinking indicator when running with only the kickoff bubble", () => {
    const { container } = render(SubagentTranscript, {
      props: { child: child(), messages: [kickoffMessage] },
    })
    // The kickoff briefing renders AND the child doesn't look stuck.
    expect(container.textContent).toContain("your assignment")
    const status = container.querySelector('[role="status"]')
    expect(status).not.toBeNull()
    expect(status?.textContent).toContain("Thinking")
  })

  it("does not show the standalone indicator once an assistant turn is the tail", () => {
    const messages: ChatMessage[] = [
      kickoffMessage,
      {
        id: "a1",
        role: "assistant",
        parts: [{ type: "text", text: "working on it" }],
      },
    ]
    const { container } = render(SubagentTranscript, {
      props: { child: child(), messages },
    })
    // The shared transcript hosts the loading affordances inside the last
    // assistant message; the standalone role="status" block stays out.
    expect(container.querySelector('[role="status"]')).toBeNull()
  })

  it("shows no indicator for a terminal child", () => {
    const { container } = render(SubagentTranscript, {
      props: {
        child: child({ state: "completed" }),
        messages: [kickoffMessage],
      },
    })
    expect(container.querySelector('[role="status"]')).toBeNull()
    expect(container.textContent).not.toContain("Thinking")
  })

  it("suppresses the standalone indicator while retrying (the transcript's retry row shows instead)", () => {
    const { container } = render(SubagentTranscript, {
      props: {
        child: child(),
        messages: [kickoffMessage],
        runtime: {
          showActivityIndicator: false,
          retry: { attempt: 1, max: 3 },
        },
      },
    })
    // Exactly one busy affordance: chat_transcript's fallback retry indicator.
    expect(container.textContent).toContain("retrying 1/3")
    expect(container.textContent).not.toContain("Thinking")
  })
})

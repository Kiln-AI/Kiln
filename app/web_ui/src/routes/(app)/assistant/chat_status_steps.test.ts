// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"

const ChatStatusSteps = (await import("./chat_status_steps.svelte")).default

afterEach(() => {
  cleanup()
})

describe("ChatStatusSteps compaction indicator (Phase 5)", () => {
  it("renders the summarizing copy when compacting", () => {
    const { getByText } = render(ChatStatusSteps, {
      props: {
        parts: [],
        isLoading: true,
        isLastMessage: true,
        compacting: true,
      },
    })
    expect(
      getByText(/Summarizing earlier messages to free up context/i),
    ).toBeTruthy()
  })

  it("does not show the normal Thinking copy while compacting", () => {
    const { queryByText } = render(ChatStatusSteps, {
      props: {
        parts: [],
        isLoading: true,
        isLastMessage: true,
        compacting: true,
      },
    })
    // The compacting message takes precedence over "Thinking".
    expect(queryByText(/^Thinking/)).toBeNull()
  })

  it("renders the normal Thinking copy when not compacting", () => {
    const { getByText, queryByText } = render(ChatStatusSteps, {
      props: {
        parts: [],
        isLoading: true,
        isLastMessage: true,
        compacting: false,
      },
    })
    expect(getByText(/Thinking/)).toBeTruthy()
    expect(
      queryByText(/Summarizing earlier messages to free up context/i),
    ).toBeNull()
  })

  it("renders nothing when neither compacting nor loading", () => {
    const { queryByText } = render(ChatStatusSteps, {
      props: {
        parts: [],
        isLoading: false,
        isLastMessage: true,
        compacting: false,
      },
    })
    expect(queryByText(/Thinking/)).toBeNull()
    expect(
      queryByText(/Summarizing earlier messages to free up context/i),
    ).toBeNull()
  })

  it("shows the compacting message even when there are parts (precedence)", () => {
    const { getByText } = render(ChatStatusSteps, {
      props: {
        parts: [{ type: "text", text: "partial" }],
        isLoading: true,
        isLastMessage: true,
        compacting: true,
      },
    })
    expect(
      getByText(/Summarizing earlier messages to free up context/i),
    ).toBeTruthy()
  })
})

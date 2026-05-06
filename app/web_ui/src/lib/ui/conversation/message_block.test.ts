// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import MessageBlock from "./message_block.svelte"
import type { TraceMessage } from "$lib/types"

afterEach(() => cleanup())

describe("MessageBlock — user role", () => {
  it("renders the user content with the user data-role marker", () => {
    const { getByTestId, container } = render(MessageBlock, {
      props: {
        role: "user",
        content: "Hello there",
      },
    })
    const block = getByTestId("message-block")
    expect(block.getAttribute("data-role")).toBe("user")
    expect(container.textContent).toContain("Hello there")
  })

  it("never renders reasoning or tool blocks for the user role", () => {
    const tool_messages: TraceMessage[] = [
      { role: "tool", content: "{}", tool_call_id: "c1" } as TraceMessage,
    ]
    const { queryByTestId } = render(MessageBlock, {
      props: {
        role: "user",
        content: "u",
        reasoning_content: "thinking",
        tool_messages,
      },
    })
    expect(queryByTestId("message-block-reasoning")).toBeNull()
    expect(queryByTestId("message-block-tools")).toBeNull()
  })
})

describe("MessageBlock — assistant role", () => {
  it("renders the assistant content with the assistant data-role marker", () => {
    const { getByTestId, container } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "General Kenobi",
      },
    })
    const block = getByTestId("message-block")
    expect(block.getAttribute("data-role")).toBe("assistant")
    expect(container.textContent).toContain("General Kenobi")
  })

  it("does not render the reasoning block when reasoning_content is null", () => {
    const { queryByTestId } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "a",
        reasoning_content: null,
      },
    })
    expect(queryByTestId("message-block-reasoning")).toBeNull()
  })

  it("renders a collapsible reasoning block inside the assistant block", () => {
    const { getByTestId } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "a",
        reasoning_content: "I thought about it",
      },
    })
    const block = getByTestId("message-block")
    const reasoning = getByTestId(
      "message-block-reasoning",
    ) as HTMLDetailsElement
    expect(reasoning.tagName.toLowerCase()).toBe("details")
    expect(reasoning.open).toBe(false)
    expect(reasoning.textContent).toContain("Reasoning")
    expect(block.contains(reasoning)).toBe(true)
  })

  it("does not render the tool block when tool_messages is empty", () => {
    const { queryByTestId } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "a",
        tool_messages: [],
      },
    })
    expect(queryByTestId("message-block-tools")).toBeNull()
  })

  it("renders a collapsible tool block inside the assistant block", () => {
    const tool_messages: TraceMessage[] = [
      {
        role: "tool",
        content: '{"output":"42"}',
        tool_call_id: "call_1",
      } as TraceMessage,
    ]
    const { getByTestId } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "a",
        tool_messages,
      },
    })
    const block = getByTestId("message-block")
    const tools = getByTestId("message-block-tools") as HTMLDetailsElement
    expect(tools.tagName.toLowerCase()).toBe("details")
    expect(tools.open).toBe(false)
    expect(tools.textContent).toContain("Tool messages (1)")
    expect(block.contains(tools)).toBe(true)
  })

  it("renders reasoning before tool calls within the assistant block", () => {
    const tool_messages: TraceMessage[] = [
      { role: "tool", content: "{}", tool_call_id: "c1" } as TraceMessage,
    ]
    const { getByTestId } = render(MessageBlock, {
      props: {
        role: "assistant",
        content: "final answer",
        reasoning_content: "thinking",
        tool_messages,
      },
    })
    const block = getByTestId("message-block")
    const children = Array.from(block.children) as HTMLElement[]
    const reasoningIdx = children.findIndex(
      (c) => c.getAttribute("data-testid") === "message-block-reasoning",
    )
    const toolsIdx = children.findIndex(
      (c) => c.getAttribute("data-testid") === "message-block-tools",
    )
    expect(reasoningIdx).toBeGreaterThanOrEqual(0)
    expect(toolsIdx).toBeGreaterThanOrEqual(0)
    expect(reasoningIdx).toBeLessThan(toolsIdx)
    expect(block.textContent).toContain("final answer")
  })
})

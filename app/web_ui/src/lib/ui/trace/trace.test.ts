// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import Trace from "./trace.svelte"
import type { Trace as TraceType, TraceMessage } from "$lib/types"

afterEach(() => cleanup())

function userMsg(content: string): TraceMessage {
  return { role: "user", content } as TraceMessage
}

function assistantMsg(
  content: string | null,
  extras: Partial<{
    tool_calls: unknown[]
    reasoning_content: string
  }> = {},
): TraceMessage {
  return {
    role: "assistant",
    content,
    ...extras,
  } as TraceMessage
}

function systemMsg(content: string): TraceMessage {
  return { role: "system", content } as TraceMessage
}

function toolMsg(content: string, tool_call_id = "call_1"): TraceMessage {
  return { role: "tool", content, tool_call_id } as TraceMessage
}

async function expandAll(container: HTMLElement): Promise<void> {
  const inputs = container.querySelectorAll<HTMLInputElement>(
    "input[type=checkbox]",
  )
  for (const input of Array.from(inputs)) {
    await fireEvent.click(input)
  }
}

describe("Trace component", () => {
  it("renders one collapsible block per message in the trace", () => {
    const trace: TraceType = [
      systemMsg("you are helpful"),
      userMsg("hi"),
      assistantMsg("hello there"),
    ]
    const { container } = render(Trace, { props: { trace } })
    const collapses = container.querySelectorAll(".collapse")
    expect(collapses.length).toBe(3)
  })

  it("shows the role label for each message block", () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u"),
      assistantMsg("a"),
      toolMsg('{"r":1}'),
    ]
    const { container } = render(Trace, { props: { trace } })
    const text = container.textContent || ""
    // Role labels use CSS uppercase, so the DOM has display-case strings.
    expect(text).toContain("System")
    expect(text).toContain("User")
    expect(text).toContain("Assistant")
    expect(text).toContain("Tool")
  })

  it("starts with all blocks collapsed (no expanded content rendered)", () => {
    const trace: TraceType = [
      userMsg("u1"),
      assistantMsg("a1", { reasoning_content: "thinking" }),
    ]
    const { container } = render(Trace, { props: { trace } })
    // Reasoning content header should not appear until expanded.
    expect(container.textContent).not.toContain("Reasoning")
  })

  it("renders content with raw Output (pre) by default for non-tool messages", async () => {
    const trace: TraceType = [assistantMsg("**bold markdown**")]
    const { container } = render(Trace, { props: { trace } })
    await expandAll(container)
    // Output renders into a <pre> with the raw text, NOT a <strong>.
    const pre = container.querySelector("pre")
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain("**bold markdown**")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders content as Markdown when markdown_content is true for non-tool messages", async () => {
    const trace: TraceType = [assistantMsg("**bold markdown**")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    // ChatMarkdown converts **bold** to <strong>bold</strong>.
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("bold markdown")
  })

  it("renders user content as Markdown when markdown_content is true", async () => {
    const trace: TraceType = [userMsg("**hello user**")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("hello user")
  })

  it("never renders tool results as Markdown even when markdown_content is true", async () => {
    const trace: TraceType = [toolMsg("**raw json please**", "call_x")]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    // Tool result must remain in a <pre> (raw Output), not as <strong>.
    const pre = container.querySelector("pre")
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain("**raw json please**")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders reasoning content as Markdown when markdown_content is true", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "**deep thought**" }),
    ]
    const { container } = render(Trace, {
      props: { trace, markdown_content: true },
    })
    await expandAll(container)
    expect(container.textContent).toContain("Reasoning")
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("deep thought")
  })

  it("renders reasoning content as raw Output by default (no markdown)", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "**deep thought**" }),
    ]
    const { container } = render(Trace, { props: { trace } })
    await expandAll(container)
    expect(container.textContent).toContain("Reasoning")
    expect(container.querySelector("strong")).toBeNull()
  })

  it("renders an empty trace without errors", () => {
    const { container } = render(Trace, { props: { trace: [] as TraceType } })
    const collapses = container.querySelectorAll(".collapse")
    expect(collapses.length).toBe(0)
  })
})

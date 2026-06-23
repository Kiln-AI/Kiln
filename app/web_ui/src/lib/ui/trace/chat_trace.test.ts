// @vitest-environment jsdom
import {
  describe,
  it,
  expect,
  afterEach,
  afterAll,
  beforeAll,
  vi,
} from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import ChatTrace from "./chat_trace.svelte"
import type { Trace as TraceType, TraceMessage } from "$lib/types"

afterEach(() => cleanup())

// jsdom's <dialog> doesn't keep the `open` flag in sync with
// showModal()/close() reliably (and didn't implement them at all before
// jsdom ~22). Force-install minimal stubs we control so we can observe
// open/close state. We restore originals in afterAll to avoid leaking.
let original_show_modal: unknown
let original_close: unknown
let installed_polyfill = false
beforeAll(() => {
  const proto = HTMLDialogElement.prototype as unknown as Record<
    string,
    unknown
  >
  original_show_modal = proto.showModal
  original_close = proto.close
  proto.showModal = function () {
    ;(this as unknown as { open: boolean }).open = true
  }
  proto.close = function () {
    ;(this as unknown as { open: boolean }).open = false
  }
  installed_polyfill = true
})
afterAll(() => {
  if (!installed_polyfill) return
  const proto = HTMLDialogElement.prototype as unknown as Record<
    string,
    unknown
  >
  proto.showModal = original_show_modal
  proto.close = original_close
  installed_polyfill = false
})

function userMsg(content: string): TraceMessage {
  return { role: "user", content } as TraceMessage
}

function assistantMsg(
  content: string | null,
  extras: Partial<{
    tool_calls: unknown[]
    reasoning_content: string
    usage: unknown
    latency_ms: number
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

function toolMsg(
  content: string,
  tool_call_id = "call_1",
  extras: Partial<{ is_error: boolean; kiln_task_tool_data: string }> = {},
): TraceMessage {
  return { role: "tool", content, tool_call_id, ...extras } as TraceMessage
}

function makeToolCall(
  id: string,
  name: string,
  args: Record<string, unknown> = {},
) {
  return {
    id,
    type: "function" as const,
    function: { name, arguments: JSON.stringify(args) },
  }
}

describe("ChatTrace component — layout & roles", () => {
  it("right-aligns user messages and left-aligns assistant messages", () => {
    const trace: TraceType = [userMsg("hello"), assistantMsg("hi there")]
    const { container } = render(ChatTrace, { props: { trace } })
    const userWrap = container.querySelector(
      "[data-testid='chat-msg-user']",
    ) as HTMLElement
    const asstWrap = container.querySelector(
      "[data-testid='chat-msg-assistant']",
    ) as HTMLElement
    expect(userWrap).not.toBeNull()
    expect(asstWrap).not.toBeNull()
    expect(userWrap.className).toContain("items-end")
    expect(asstWrap.className).toContain("items-start")
  })

  it("does NOT render tool messages as their own bubble", () => {
    const trace: TraceType = [
      userMsg("u"),
      assistantMsg(null, { tool_calls: [makeToolCall("c1", "lookup")] }),
      toolMsg('{"output": "42"}', "c1"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    // No standalone tool bubble — tool results nest inside the assistant turn.
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-user'], [data-testid='chat-msg-assistant'], [data-testid='chat-msg-system']",
    )
    expect(bubbles.length).toBe(2)
  })

  it("renders user content as markdown by default", () => {
    const trace: TraceType = [userMsg("**bold**")]
    const { container } = render(ChatTrace, { props: { trace } })
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("bold")
  })

  it("renders assistant content as markdown by default", () => {
    const trace: TraceType = [assistantMsg("**bold answer**")]
    const { container } = render(ChatTrace, { props: { trace } })
    const strong = container.querySelector("strong")
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("bold answer")
  })

  it("splits an assistant message with reasoning + content into two bubbles (reasoning first)", () => {
    const trace: TraceType = [
      assistantMsg("the answer", { reasoning_content: "step-by-step" }),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(2)
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-thinking']"),
    ).not.toBeNull()
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-content']"),
    ).toBeNull()
    expect(
      bubbles[1].querySelector("[data-testid='chat-msg-content']"),
    ).not.toBeNull()
    expect(
      bubbles[1].querySelector("[data-testid='chat-msg-thinking']"),
    ).toBeNull()
  })

  it("renders a single reasoning-only bubble when the assistant has only reasoning", () => {
    const trace: TraceType = [
      assistantMsg(null, { reasoning_content: "thinking out loud" }),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(1)
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-thinking']"),
    ).not.toBeNull()
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-content']"),
    ).toBeNull()
  })

  it("splits reasoning + content + N tool calls into 2 + N bubbles", () => {
    const trace: TraceType = [
      assistantMsg("here's the plan", {
        reasoning_content: "thinking",
        tool_calls: [makeToolCall("c1", "lookup"), makeToolCall("c2", "fetch")],
      }),
      toolMsg('{"output": "r1"}', "c1"),
      toolMsg('{"output": "r2"}', "c2"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(4)
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-thinking']"),
    ).not.toBeNull()
    expect(
      bubbles[1].querySelector("[data-testid='chat-msg-content']"),
    ).not.toBeNull()
    expect(
      bubbles[2].querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
    expect(
      bubbles[3].querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
  })

  it("splits an assistant message with content + N tool calls into 1 + N bubbles", () => {
    const trace: TraceType = [
      assistantMsg("here is what I'll do", {
        tool_calls: [makeToolCall("c1", "lookup"), makeToolCall("c2", "fetch")],
      }),
      toolMsg('{"output": "r1"}', "c1"),
      toolMsg('{"output": "r2"}', "c2"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(3)
    // First bubble holds the content; following bubbles each hold one tool call.
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-content']"),
    ).not.toBeNull()
    expect(
      bubbles[0].querySelector("[data-testid='chat-msg-toolcall']"),
    ).toBeNull()
    expect(
      bubbles[1].querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
    expect(
      bubbles[2].querySelector("[data-testid='chat-msg-toolcall']"),
    ).not.toBeNull()
  })

  it("renders a single bubble when an assistant message has only content (no tool_calls)", () => {
    const trace: TraceType = [assistantMsg("just an answer")]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(1)
  })

  it("renders one bubble per tool call when an assistant message has only tool_calls", () => {
    const trace: TraceType = [
      assistantMsg(null, {
        tool_calls: [makeToolCall("c1", "lookup"), makeToolCall("c2", "fetch")],
      }),
      toolMsg('{"output": "r1"}', "c1"),
      toolMsg('{"output": "r2"}', "c2"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(2)
  })

  it("renders a usage actions row for the assistant turn, independent of thinking expansion", () => {
    const trace: TraceType = [
      assistantMsg(null, {
        reasoning_content: "deep thought",
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, show_per_message_usage: true },
    })
    // One actions row for the turn, present without expanding (it's revealed
    // on hover via CSS, not gated on the thinking toggle).
    const metas = container.querySelectorAll("[data-testid='chat-msg-meta']")
    expect(metas.length).toBe(1)
    expect(
      metas[0].querySelector("button[aria-label='View turn usage']"),
    ).not.toBeNull()
  })

  it("renders a single usage actions row per assistant turn, outside the bubbles", () => {
    const trace: TraceType = [
      assistantMsg("answer", {
        tool_calls: [makeToolCall("c1", "lookup"), makeToolCall("c2", "fetch")],
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
      toolMsg('{"output": "ok1"}', "c1"),
      toolMsg('{"output": "ok2"}', "c2"),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, show_per_message_usage: true },
    })
    // Exactly one actions row for the whole turn — not one per bubble.
    const metas = container.querySelectorAll("[data-testid='chat-msg-meta']")
    expect(metas.length).toBe(1)
    // And it lives outside the individual message bubbles.
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(3)
    bubbles.forEach((b) => {
      expect(b.querySelector("[data-testid='chat-msg-meta']")).toBeNull()
    })
  })

  it("places the user metadata row inside the user bubble", () => {
    const trace: TraceType = [
      userMsg("hello"),
      assistantMsg("hi"),
      userMsg("again"),
    ]
    const forkable_run_ids = [null, null, "run-2"]
    const { container } = render(ChatTrace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    const userBubbles = container.querySelectorAll(
      "[data-testid='chat-msg-user']",
    )
    expect(userBubbles.length).toBe(2)
    // Fork button should be inside the second user bubble.
    expect(
      userBubbles[1].querySelector("button[aria-label='Fork from this turn']"),
    ).not.toBeNull()
  })
})

describe("ChatTrace component — thinking", () => {
  it("starts with thinking collapsed", () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "step-by-step plan" }),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    // Header is visible.
    expect(container.textContent).toContain("Thinking")
    // Body text is NOT visible until expanded.
    expect(container.textContent).not.toContain("step-by-step plan")
  })

  it("expands thinking when the user clicks anywhere on the bubble (not just the toggle)", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "secret thought" }),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const thinkingTestid = container.querySelector(
      "[data-testid='chat-msg-thinking']",
    ) as HTMLElement
    // The bubble is the parent of the chat-msg-thinking marker.
    const bubble = thinkingTestid.parentElement as HTMLElement
    expect(container.textContent).not.toContain("secret thought")
    await fireEvent.click(bubble)
    expect(container.textContent).toContain("secret thought")
  })

  it("clicking the toggle inside the bubble while expanded collapses it (does not re-expand via container click)", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "secret thought" }),
    ]
    const { container, getByText } = render(ChatTrace, { props: { trace } })
    // Expand via container click.
    const thinkingTestid = container.querySelector(
      "[data-testid='chat-msg-thinking']",
    ) as HTMLElement
    const bubble = thinkingTestid.parentElement as HTMLElement
    await fireEvent.click(bubble)
    expect(container.textContent).toContain("secret thought")
    // Now click the toggle button. The button's |stopPropagation must keep
    // the container's expand-only handler from re-expanding.
    await fireEvent.click(getByText("Thinking"))
    expect(container.textContent).not.toContain("secret thought")
  })

  it("expands thinking when the toggle is clicked", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "deep thought" }),
    ]
    const { container, getByText } = render(ChatTrace, { props: { trace } })
    await fireEvent.click(getByText("Thinking"))
    expect(container.textContent).toContain("deep thought")
  })

  it("renders thinking content as markdown when expanded", async () => {
    const trace: TraceType = [
      assistantMsg("done", { reasoning_content: "**emphasis**" }),
    ]
    const { container, getByText } = render(ChatTrace, { props: { trace } })
    await fireEvent.click(getByText("Thinking"))
    const strong = container.querySelector(
      "[data-testid='chat-msg-thinking'] strong",
    )
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe("emphasis")
  })

  it("omits the thinking section when reasoning_content is empty", () => {
    const trace: TraceType = [assistantMsg("just an answer")]
    const { container } = render(ChatTrace, { props: { trace } })
    expect(
      container.querySelector("[data-testid='chat-msg-thinking']"),
    ).toBeNull()
  })
})

describe("ChatTrace component — tool calls", () => {
  it("renders one bubble per tool call with a 'Toolcall: {name}' label, collapsed by default", () => {
    const trace: TraceType = [
      assistantMsg(null, {
        tool_calls: [
          makeToolCall("c1", "lookup"),
          makeToolCall("c2", "fetch"),
          makeToolCall("c3", "save"),
        ],
      }),
      toolMsg('{"output": "r1"}', "c1"),
      toolMsg('{"output": "r2"}', "c2"),
      toolMsg('{"output": "r3"}', "c3"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const tcBubbles = container.querySelectorAll(
      "[data-testid='chat-msg-toolcall']",
    )
    expect(tcBubbles.length).toBe(3)
    expect(container.textContent).toContain("Toolcall:")
    expect(container.textContent).toContain("lookup")
    expect(container.textContent).toContain("fetch")
    expect(container.textContent).toContain("save")
    // No expanded card visible yet.
    expect(
      container.querySelectorAll("[data-testid='chat-tool-call']").length,
    ).toBe(0)
    // No grouping summary like "3 tool calls" anymore.
    expect(container.textContent).not.toContain("3 tool calls")
  })

  it("expands a tool-call bubble when the user clicks anywhere on it (not just the toggle)", async () => {
    const trace: TraceType = [
      assistantMsg(null, {
        tool_calls: [makeToolCall("c1", "lookup", { q: "secret-arg" })],
      }),
      toolMsg('{"output": "ok"}', "c1"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const tcTestid = container.querySelector(
      "[data-testid='chat-msg-toolcall']",
    ) as HTMLElement
    const bubble = tcTestid.parentElement as HTMLElement
    // No args visible while collapsed.
    expect(container.textContent).not.toContain("secret-arg")
    await fireEvent.click(bubble)
    expect(container.textContent).toContain("secret-arg")
  })

  it("expands a tool-call bubble and reveals args + matching tool result", async () => {
    const trace: TraceType = [
      assistantMsg(null, {
        tool_calls: [makeToolCall("c1", "lookup", { q: "kiln" })],
      }),
      toolMsg('{"output": "answer-from-tool"}', "c1"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const tcBubble = container.querySelector(
      "[data-testid='chat-msg-toolcall']",
    ) as HTMLElement
    const toggle = tcBubble.querySelector("button") as HTMLButtonElement
    await fireEvent.click(toggle)
    const cards = container.querySelectorAll("[data-testid='chat-tool-call']")
    expect(cards.length).toBe(1)
    const card = cards[0] as HTMLElement
    expect(card.textContent).toContain("kiln")
    expect(card.textContent).toContain("Tool Result")
    expect(card.textContent).toContain("answer-from-tool")
  })

  it("expands tool-call bubbles independently", async () => {
    const trace: TraceType = [
      assistantMsg(null, {
        tool_calls: [
          makeToolCall("c1", "lookup", { q: "first" }),
          makeToolCall("c2", "fetch", { q: "second" }),
        ],
      }),
      toolMsg('{"output": "r1"}', "c1"),
      toolMsg('{"output": "r2"}', "c2"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const tcBubbles = container.querySelectorAll(
      "[data-testid='chat-msg-toolcall']",
    )
    expect(tcBubbles.length).toBe(2)
    // Expand only the second one.
    const secondToggle = tcBubbles[1].querySelector(
      "button",
    ) as HTMLButtonElement
    await fireEvent.click(secondToggle)
    expect(
      container.querySelectorAll("[data-testid='chat-tool-call']").length,
    ).toBe(1)
    expect(container.textContent).toContain("second")
    expect(container.textContent).not.toContain("first")
  })

  it("marks the tool result as an error when the tool message reports is_error", async () => {
    const trace: TraceType = [
      assistantMsg(null, { tool_calls: [makeToolCall("c1", "lookup")] }),
      toolMsg("boom", "c1", { is_error: true }),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const toggle = container.querySelector(
      "[data-testid='chat-msg-toolcall'] button",
    ) as HTMLButtonElement
    await fireEvent.click(toggle)
    expect(container.textContent).toContain("Tool Error")
  })

  it("indicates when a tool call has no matching result", async () => {
    const trace: TraceType = [
      assistantMsg(null, { tool_calls: [makeToolCall("c1", "lookup")] }),
      // no matching tool message
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    const toggle = container.querySelector(
      "[data-testid='chat-msg-toolcall'] button",
    ) as HTMLButtonElement
    await fireEvent.click(toggle)
    expect(container.textContent).toContain("No tool result recorded")
  })
})

describe("ChatTrace component — system prompt", () => {
  it("does not render system messages at all (no toggle, no content)", () => {
    const trace: TraceType = [systemMsg("you are helpful"), userMsg("hi")]
    const { container } = render(ChatTrace, { props: { trace } })
    expect(
      container.querySelector("[data-testid='chat-msg-system']"),
    ).toBeNull()
    expect(container.textContent).not.toContain("you are helpful")
    expect(container.textContent).not.toContain("system prompt")
  })

  it("does not render developer messages either", () => {
    const trace: TraceType = [
      { role: "developer", content: "internal directive" } as TraceMessage,
      userMsg("hi"),
    ]
    const { container } = render(ChatTrace, { props: { trace } })
    expect(
      container.querySelector("[data-testid='chat-msg-system']"),
    ).toBeNull()
    expect(container.textContent).not.toContain("internal directive")
  })
})

describe("ChatTrace component — fork affordance", () => {
  function fork_button(container: HTMLElement) {
    return container.querySelectorAll<HTMLButtonElement>(
      'button[aria-label="Fork from this turn"]',
    )
  }

  it("renders a fork button on user messages that are forkable", () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const forkable_run_ids = [null, null, null, "run-2", null]
    const { container } = render(ChatTrace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    expect(fork_button(container).length).toBe(1)
  })

  it("does NOT render a fork button on assistant messages even if forkable_run_ids[i] is set", () => {
    const trace: TraceType = [userMsg("u1"), assistantMsg("a1")]
    const forkable_run_ids = ["run-u", "run-a"]
    const { container } = render(ChatTrace, {
      props: { trace, forkable_run_ids, on_fork: vi.fn() },
    })
    // Only the user msg gets a fork button.
    expect(fork_button(container).length).toBe(1)
  })

  it("invokes on_fork with the mapped run id and trace index", async () => {
    const trace: TraceType = [
      systemMsg("s"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
    ]
    const forkable_run_ids = [null, null, null, "run-leaf"]
    const on_fork = vi.fn()
    const { container } = render(ChatTrace, {
      props: { trace, forkable_run_ids, on_fork },
    })
    const button = fork_button(container)[0]
    expect(button).toBeDefined()
    await fireEvent.click(button)
    expect(on_fork).toHaveBeenCalledTimes(1)
    expect(on_fork).toHaveBeenCalledWith("run-leaf", 3)
  })

  it("does NOT render any fork button when on_fork is not provided", () => {
    const trace: TraceType = [userMsg("u1")]
    const forkable_run_ids = ["run-1"]
    const { container } = render(ChatTrace, {
      props: { trace, forkable_run_ids },
    })
    expect(fork_button(container).length).toBe(0)
  })

  it("hides messages at or after truncate_at_trace_index", () => {
    const trace: TraceType = [
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, truncate_at_trace_index: 2 },
    })
    // Only indices 0..1 render.
    const bubbles = container.querySelectorAll(
      "[data-testid='chat-msg-user'], [data-testid='chat-msg-assistant']",
    )
    expect(bubbles.length).toBe(2)
  })
})

describe("ChatTrace component — usage info row", () => {
  it("renders a usage info button when show_per_message_usage and message has usage", () => {
    const trace: TraceType = [
      assistantMsg("answer", {
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, show_per_message_usage: true },
    })
    expect(
      container.querySelector("button[aria-label='View turn usage']"),
    ).not.toBeNull()
  })

  it("labels the usage button so users know what it does", () => {
    const trace: TraceType = [
      assistantMsg("answer", {
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, show_per_message_usage: true },
    })
    const button = container.querySelector(
      "button[aria-label='View turn usage']",
    ) as HTMLButtonElement
    expect(button).not.toBeNull()
    expect(button.textContent).toContain("Usage")
  })

  it("does not render usage button when show_per_message_usage is false", () => {
    const trace: TraceType = [
      assistantMsg("answer", {
        usage: { input_tokens: 10, output_tokens: 5 },
      }),
    ]
    const { container } = render(ChatTrace, {
      props: { trace, show_per_message_usage: false },
    })
    expect(
      container.querySelector("button[aria-label='View turn usage']"),
    ).toBeNull()
  })

  it("opens a usage breakdown dialog when the usage info button is clicked", async () => {
    const trace: TraceType = [
      assistantMsg("answer", {
        usage: {
          input_tokens: 10,
          output_tokens: 5,
          total_tokens: 15,
          cost: 0.0001234,
        },
        latency_ms: 1234,
      }),
    ]
    const { container, baseElement } = render(ChatTrace, {
      props: { trace, show_per_message_usage: true },
    })
    const button = container.querySelector(
      "button[aria-label='View turn usage']",
    ) as HTMLButtonElement
    await fireEvent.click(button)
    // The page mounts two Dialogs (subtask trace + usage info). Pick the
    // one whose heading is "Usage".
    const dialogs = Array.from(
      baseElement.querySelectorAll<HTMLDialogElement>("dialog"),
    )
    const usage_dialog = dialogs.find((d) =>
      (d.textContent ?? "").includes("Usage"),
    )
    expect(usage_dialog).toBeDefined()
    const text = usage_dialog!.textContent ?? ""
    expect(text).toContain("Cost")
    expect(text).toContain("$0.000123")
    expect(text).toContain("Total tokens")
    expect(text).toContain("15")
    expect(text).toContain("Input tokens")
    expect(text).toContain("Output tokens")
    expect(text).toContain("Latency")
  })
})

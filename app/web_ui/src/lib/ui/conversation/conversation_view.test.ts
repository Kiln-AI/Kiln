// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import ConversationView, {
  build_rendered_messages,
} from "./conversation_view.svelte"
import type { Task, Trace, TraceMessage } from "$lib/types"

afterEach(() => cleanup())

const fake_task = { id: "task-1", name: "Task" } as unknown as Task

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

function toolMsg(content: string, tool_call_id = "call_1"): TraceMessage {
  return { role: "tool", content, tool_call_id } as TraceMessage
}

function systemMsg(content: string): TraceMessage {
  return { role: "system", content } as TraceMessage
}

describe("build_rendered_messages", () => {
  it("renders messages flat in trace order and skips the system prelude", () => {
    const trace: Trace = [
      systemMsg("you are helpful"),
      userMsg("hi"),
      assistantMsg("hello"),
      userMsg("how are you"),
      assistantMsg("fine thanks"),
    ]
    const rendered = build_rendered_messages(trace)
    expect(rendered.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ])
    expect(rendered.map((m) => m.content)).toEqual([
      "hi",
      "hello",
      "how are you",
      "fine thanks",
    ])
  })

  it("renders 6 entries (3 user + 3 assistant) for a 3-turn trace", () => {
    const trace: Trace = [
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
      userMsg("u3"),
      assistantMsg("a3"),
    ]
    const rendered = build_rendered_messages(trace)
    expect(rendered).toHaveLength(6)
    expect(rendered.map((m) => m.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
      "user",
      "assistant",
    ])
    expect(rendered.map((m) => m.content)).toEqual([
      "u1",
      "a1",
      "u2",
      "a2",
      "u3",
      "a3",
    ])
  })

  it("skips developer messages too", () => {
    const developer = {
      role: "developer",
      content: "secret instructions",
    } as TraceMessage
    const trace: Trace = [developer, userMsg("u1"), assistantMsg("a1")]
    const rendered = build_rendered_messages(trace)
    expect(rendered).toHaveLength(2)
    expect(rendered[0].role).toBe("user")
    expect(rendered[0].content).toBe("u1")
    expect(rendered[1].role).toBe("assistant")
    expect(rendered[1].content).toBe("a1")
  })

  it("folds tool call/result messages into the next assistant block", () => {
    const trace: Trace = [
      userMsg("call the weather tool"),
      assistantMsg(null, {
        tool_calls: [
          { id: "c1", type: "function", function: { name: "weather" } },
        ],
      }),
      toolMsg('{"temp":72}', "c1"),
      assistantMsg("It is 72."),
    ]
    const rendered = build_rendered_messages(trace)
    expect(rendered).toHaveLength(2)
    expect(rendered[0].role).toBe("user")
    expect(rendered[0].content).toBe("call the weather tool")
    expect(rendered[1].role).toBe("assistant")
    expect(rendered[1].content).toBe("It is 72.")
    expect(rendered[1].tool_messages.length).toBe(2)
    expect(rendered[1].tool_messages[0].role).toBe("assistant")
    expect(rendered[1].tool_messages[1].role).toBe("tool")
  })

  it("captures reasoning_content from the assistant message", () => {
    const trace: Trace = [
      userMsg("u1"),
      assistantMsg("a1", { reasoning_content: "thinking" }),
    ]
    const rendered = build_rendered_messages(trace)
    expect(rendered[1].role).toBe("assistant")
    expect(rendered[1].reasoning_content).toBe("thinking")
  })

  it("flattens content arrays of text parts", () => {
    const arrUser: TraceMessage = {
      role: "user",
      content: [
        { type: "text", text: "hello " },
        { type: "text", text: "world" },
      ],
    } as unknown as TraceMessage
    const trace: Trace = [arrUser, assistantMsg("ok")]
    const rendered = build_rendered_messages(trace)
    expect(rendered[0].content).toBe("hello \nworld")
  })
})

describe("ConversationView component", () => {
  it("renders one message-block per non-system message", () => {
    const trace: Trace = [
      systemMsg("sys"),
      userMsg("u1"),
      assistantMsg("a1"),
      userMsg("u2"),
      assistantMsg("a2"),
    ]
    const { getAllByTestId, getByTestId } = render(ConversationView, {
      props: { trace, task: fake_task },
    })
    expect(getByTestId("conversation-view")).not.toBeNull()
    const blocks = getAllByTestId("message-block")
    expect(blocks).toHaveLength(4)
    expect(blocks.map((b) => b.getAttribute("data-role"))).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ])
  })

  it("renders messages in trace order", () => {
    const trace: Trace = [
      userMsg("first"),
      assistantMsg("second"),
      userMsg("third"),
      assistantMsg("fourth"),
    ]
    const { getAllByTestId } = render(ConversationView, {
      props: { trace, task: fake_task },
    })
    const blocks = getAllByTestId("message-block")
    expect(blocks.map((b) => b.textContent?.trim())).toEqual([
      "first",
      "second",
      "third",
      "fourth",
    ])
  })

  it("renders reasoning and tool blocks inside the assistant message-block, not as their own", () => {
    const trace: Trace = [
      userMsg("ask"),
      assistantMsg(null, {
        tool_calls: [
          { id: "c1", type: "function", function: { name: "weather" } },
        ],
      }),
      toolMsg('{"temp":72}', "c1"),
      assistantMsg("done", { reasoning_content: "thinking" }),
    ]
    const { getAllByTestId, getByTestId } = render(ConversationView, {
      props: { trace, task: fake_task },
    })
    const blocks = getAllByTestId("message-block")
    expect(blocks).toHaveLength(2)
    const assistantBlock = blocks[1]
    expect(assistantBlock.getAttribute("data-role")).toBe("assistant")
    const reasoning = getByTestId("message-block-reasoning")
    const tools = getByTestId("message-block-tools")
    expect(assistantBlock.contains(reasoning)).toBe(true)
    expect(assistantBlock.contains(tools)).toBe(true)
  })

  it("skips leading system and developer messages", () => {
    const developer = {
      role: "developer",
      content: "dev",
    } as TraceMessage
    const trace: Trace = [
      systemMsg("sys"),
      developer,
      userMsg("u1"),
      assistantMsg("a1"),
    ]
    const { getAllByTestId } = render(ConversationView, {
      props: { trace, task: fake_task },
    })
    const blocks = getAllByTestId("message-block")
    expect(blocks).toHaveLength(2)
    expect(blocks.map((b) => b.getAttribute("data-role"))).toEqual([
      "user",
      "assistant",
    ])
  })

  it("renders nothing inside the wrapper for an empty trace", () => {
    const { getByTestId, queryAllByTestId } = render(ConversationView, {
      props: { trace: [] as Trace, task: fake_task },
    })
    expect(getByTestId("conversation-view")).not.toBeNull()
    expect(queryAllByTestId("message-block")).toHaveLength(0)
  })
})

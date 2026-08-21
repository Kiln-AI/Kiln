import { describe, expect, it } from "vitest"
import {
  hydrateSessionFromSnapshot,
  parseSubagentReport,
  stripAppUiContext,
  stripInternalFraming,
  userChatMessageFromContent,
  type ChatSessionSnapshot,
} from "./session_messages"

function snap(
  id: string,
  trace: ChatSessionSnapshot["task_run"]["trace"],
  rootId?: string,
): ChatSessionSnapshot {
  return { id, task_run: { trace }, ...(rootId ? { root_id: rootId } : {}) }
}

describe("hydrateSessionFromSnapshot", () => {
  it("maps user and assistant trace messages without any trace keying", () => {
    const { messages, rootId } = hydrateSessionFromSnapshot(
      snap("trace-sess", [
        { role: "user", content: "Hello" },
        { role: "assistant", content: "Hi there" },
      ]),
    )
    expect(messages).toHaveLength(2)
    expect(messages[0].role).toBe("user")
    expect(messages[0].content).toBe("Hello")
    expect(messages[1].role).toBe("assistant")
    expect(messages[1].parts?.[0]).toEqual({ type: "text", text: "Hi there" })
    // Phase 5: no message carries a trace id anymore (the old world stamped
    // the last assistant with the snapshot id as the browser's continuation
    // key) and the leaf-shaped snapshot id is not surfaced — only the
    // durable root_id is (absent here → null).
    expect(messages[1].traceId).toBeUndefined()
    expect(rootId).toBeNull()
  })

  it("returns the snapshot's durable root_id when the desktop passes it through", () => {
    const { rootId } = hydrateSessionFromSnapshot(
      snap("leaf-2", [{ role: "user", content: "Hello" }], "1234567890_root"),
    )
    expect(rootId).toBe("1234567890_root")
  })

  it("ignores reasoning_content (reasoning is not surfaced in the UI)", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("t2", [
        {
          role: "assistant",
          content: "answer",
          reasoning_content: "think",
        },
      ]),
    )
    expect(messages[0].parts).toEqual([{ type: "text", text: "answer" }])
  })

  it("maps tool_calls and tool messages", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("t3", [
        {
          role: "assistant",
          tool_calls: [
            {
              id: "tc1",
              type: "function",
              function: { name: "math__add", arguments: '{"a":1,"b":2}' },
            },
          ],
        },
        { role: "tool", tool_call_id: "tc1", content: "3" },
      ]),
    )
    expect(messages).toHaveLength(1)
    const parts = messages[0].parts!
    expect(parts[0]).toMatchObject({
      type: "tool-math__add",
      toolCallId: "tc1",
      toolName: "math__add",
      input: { a: 1, b: 2 },
      output: "3",
    })
  })

  it("skips system and developer messages", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("x", [
        { role: "system", content: "You are helpful" },
        { role: "developer", content: "internal" },
        { role: "user", content: "ok" },
      ]),
    )
    expect(messages.map((m) => m.role)).toEqual(["user"])
  })

  it("skips tool messages from the trace (folded into assistant parts)", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("x", [
        { role: "tool", tool_call_id: "orphan", content: "result" },
        { role: "user", content: "ok" },
      ]),
    )
    expect(messages.map((m) => m.role)).toEqual(["user"])
  })

  it("handles empty trace", () => {
    const { messages, rootId } = hydrateSessionFromSnapshot(snap("empty", []))
    expect(messages).toHaveLength(0)
    expect(rootId).toBeNull()
  })

  it("handles null trace", () => {
    const { messages } = hydrateSessionFromSnapshot(snap("null-trace", null))
    expect(messages).toHaveLength(0)
  })

  it("parses tool call arguments that are not valid JSON as strings", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("bad-args", [
        {
          role: "assistant",
          tool_calls: [
            {
              id: "tc2",
              type: "function",
              function: { name: "echo", arguments: "not-json" },
            },
          ],
        },
      ]),
    )
    const part = messages[0].parts![0]
    expect("input" in part && part.input).toBe("not-json")
  })

  it("strips <new_app_ui_context> from the first user message", () => {
    const header =
      "<new_app_ui_context>\nPath: /assistant\nPage Name: Assistant\n</new_app_ui_context>"
    const { messages } = hydrateSessionFromSnapshot(
      snap("ctx", [
        { role: "user", content: `${header}\nHello agent` },
        { role: "assistant", content: "Hi" },
      ]),
    )
    expect(messages[0].content).toBe("Hello agent")
  })

  it("strips <new_app_ui_context> from subsequent user messages too", () => {
    const header =
      "<new_app_ui_context>\nCurrent Task: summarize\n</new_app_ui_context>"
    const { messages } = hydrateSessionFromSnapshot(
      snap("ctx2", [
        { role: "user", content: "First message" },
        { role: "assistant", content: "ok" },
        { role: "user", content: `${header}\nSecond message` },
      ]),
    )
    expect(messages[0].content).toBe("First message")
    expect(messages[2].content).toBe("Second message")
  })

  it("leaves user messages without context tags unchanged", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("no-ctx", [{ role: "user", content: "plain question" }]),
    )
    expect(messages[0].content).toBe("plain question")
  })

  it("skips empty assistant messages (no content, no tool_calls)", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("empty-asst", [
        { role: "user", content: "list projects" },
        { role: "assistant", content: "", tool_calls: [] },
        { role: "assistant", content: "", tool_calls: [] },
        { role: "assistant", content: "", tool_calls: [] },
        {
          role: "assistant",
          content: "",
          tool_calls: [
            {
              id: "tc1",
              type: "function",
              function: {
                name: "call_kiln_api",
                arguments: '{"method":"GET"}',
              },
            },
          ],
        },
        { role: "tool", tool_call_id: "tc1", content: "result" },
        { role: "assistant", content: "Here are your projects" },
      ]),
    )
    expect(messages).toHaveLength(3)
    expect(messages[0].role).toBe("user")
    expect(messages[1].role).toBe("assistant")
    expect(messages[1].parts?.[0]).toMatchObject({
      type: "tool-call_kiln_api",
      output: "result",
    })
    expect(messages[2].role).toBe("assistant")
    expect(messages[2].parts?.[0]).toEqual({
      type: "text",
      text: "Here are your projects",
    })
  })
})

describe("stripAppUiContext", () => {
  it("removes a single context block with trailing newline", () => {
    const input =
      "<new_app_ui_context>\nPath: /assistant\n</new_app_ui_context>\nHello"
    expect(stripAppUiContext(input)).toBe("Hello")
  })

  it("removes multiple context blocks", () => {
    const input =
      "<new_app_ui_context>\nA\n</new_app_ui_context>\n<new_app_ui_context>\nB\n</new_app_ui_context>\nHi"
    expect(stripAppUiContext(input)).toBe("Hi")
  })

  it("returns the string unchanged when no context block is present", () => {
    expect(stripAppUiContext("just text")).toBe("just text")
  })

  it("returns empty string when the entire content is a context block", () => {
    const input = "<new_app_ui_context>\nPath: /\n</new_app_ui_context>"
    expect(stripAppUiContext(input)).toBe("")
  })

  it("handles empty string", () => {
    expect(stripAppUiContext("")).toBe("")
  })
})

describe("stripInternalFraming", () => {
  it("removes a leading auto-mode side-note <system-reminder> wrapper", () => {
    const input =
      "<system-reminder>This message arrived while you are working autonomously…</system-reminder>\n\nmy name is bobby"
    expect(stripInternalFraming(input)).toBe("my name is bobby")
  })

  it("removes both an app-UI context block and a system-reminder", () => {
    const input =
      "<new_app_ui_context>\nPath: /assistant\n</new_app_ui_context>\n<system-reminder>side note</system-reminder>\n\nhello"
    expect(stripInternalFraming(input)).toBe("hello")
  })

  it("leaves a plain message untouched", () => {
    expect(stripInternalFraming("just text")).toBe("just text")
  })

  it("handles empty string", () => {
    expect(stripInternalFraming("")).toBe("")
  })
})

describe("hydrateSessionFromSnapshot strips injected-message framing", () => {
  it("renders the raw user message for a persisted side-note-wrapped inject", () => {
    const snapshot: ChatSessionSnapshot = {
      id: "trace-inject",
      task_run: {
        trace: [
          {
            role: "user",
            content:
              "<system-reminder>Treat it as a side note…</system-reminder>\n\nmy name is bobby whats yours?",
          },
          { role: "assistant", content: "Hey Bobby!" },
        ],
      },
    } as unknown as ChatSessionSnapshot
    const { messages } = hydrateSessionFromSnapshot(snapshot)
    expect(messages[0].role).toBe("user")
    expect(messages[0].content).toBe("my name is bobby whats yours?")
  })
})

describe("parseSubagentReport", () => {
  const frame = (attrs: string, body: string) =>
    `<subagent_report ${attrs}>\n${body}\n</subagent_report>`

  it("parses a well-formed report frame", () => {
    const parsed = parseSubagentReport(
      frame(
        'id="sa_abc123" agent_type="general" status="completed" title="Eval sweep"',
        "## Findings\n\nAll good.",
      ),
    )
    expect(parsed).not.toBeNull()
    expect(parsed?.info).toEqual({
      id: "sa_abc123",
      agentType: "general",
      status: "completed",
      title: "Eval sweep",
    })
    expect(parsed?.body).toBe("## Findings\n\nAll good.")
  })

  it("unescapes quotes (and other escaped entities) in the title", () => {
    // The server escapes the name with & → &amp;, " → &quot;, < → &lt;.
    const parsed = parseSubagentReport(
      frame(
        'id="sa_x" agent_type="general" status="failed" title="Check &quot;prod&quot; &amp; &lt;staging>"',
        "body",
      ),
    )
    expect(parsed?.info.title).toBe('Check "prod" & <staging>')
    expect(parsed?.info.status).toBe("failed")
  })

  it("returns null for a non-report user message", () => {
    expect(parseSubagentReport("just a normal message")).toBeNull()
    expect(
      parseSubagentReport("mentions <subagent_report but is not a frame"),
    ).toBeNull()
    // A frame with trailing content after the close tag is not a pure report
    // message and stays a normal user bubble.
    expect(
      parseSubagentReport(
        `${frame('id="sa_x" agent_type="g" status="completed" title="t"', "body")}\nand my own words`,
      ),
    ).toBeNull()
  })

  it("tolerates surrounding whitespace", () => {
    const parsed = parseSubagentReport(
      `\n  ${frame('id="sa_x" agent_type="g" status="completed" title="t"', "body")}\n`,
    )
    expect(parsed?.body).toBe("body")
  })
})

describe("userChatMessageFromContent", () => {
  it("marks report frames and sets content to the body", () => {
    const msg = userChatMessageFromContent(
      '<subagent_report id="sa_1" agent_type="general" status="completed" title="T">\nreport body\n</subagent_report>',
      "echo-1",
    )
    expect(msg.role).toBe("user")
    expect(msg.content).toBe("report body")
    expect(msg.subagentReport).toEqual({
      id: "sa_1",
      agentType: "general",
      status: "completed",
      title: "T",
    })
    expect(msg.echoId).toBe("echo-1")
  })

  it("leaves plain user content untouched", () => {
    const msg = userChatMessageFromContent("hello there")
    expect(msg.content).toBe("hello there")
    expect(msg.subagentReport).toBeUndefined()
  })
})

describe("hydrateSessionFromSnapshot sub-agent reports", () => {
  it("marks a report-framed user message and strips the frame", () => {
    const { messages } = hydrateSessionFromSnapshot(
      snap("t-report", [
        { role: "user", content: "run the sweep" },
        { role: "assistant", content: "Spawning…" },
        {
          role: "user",
          content:
            '<subagent_report id="sa_9" agent_type="general" status="timeout" title="Sweep">\npartial results\n</subagent_report>',
        },
      ]),
    )
    expect(messages).toHaveLength(3)
    expect(messages[2].role).toBe("user")
    expect(messages[2].content).toBe("partial results")
    expect(messages[2].subagentReport).toMatchObject({
      id: "sa_9",
      status: "timeout",
      title: "Sweep",
    })
    // The normal user message is untouched.
    expect(messages[0].subagentReport).toBeUndefined()
  })
})

describe("hydrateSessionFromSnapshot context_usage", () => {
  it("returns normalized contextUsage from snapshot.context_usage", () => {
    const snapshot: ChatSessionSnapshot = {
      id: "trace-ctx",
      task_run: { trace: [{ role: "user", content: "hi" }] },
      context_usage: {
        context_tokens: 120,
        context_limit: 200,
        context_percent: 0.6,
        compacted: true,
      },
    }
    const { contextUsage } = hydrateSessionFromSnapshot(snapshot)
    expect(contextUsage).toEqual({
      context_tokens: 120,
      context_limit: 200,
      context_percent: 0.6,
      compacted: true,
    })
  })

  it("returns null contextUsage when the field is absent", () => {
    const { contextUsage } = hydrateSessionFromSnapshot(
      snap("trace-no-ctx", [{ role: "user", content: "hi" }]),
    )
    expect(contextUsage).toBeNull()
  })

  it("returns null contextUsage when the field carries no numbers", () => {
    const snapshot: ChatSessionSnapshot = {
      id: "trace-empty-ctx",
      task_run: { trace: [{ role: "user", content: "hi" }] },
      context_usage: { compacted: false },
    }
    expect(hydrateSessionFromSnapshot(snapshot).contextUsage).toBeNull()
  })
})

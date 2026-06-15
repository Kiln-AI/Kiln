import { describe, expect, it, vi } from "vitest"
import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"
import {
  streamChat,
  resumePendingToolCalls,
  chatExecuteToolsUrl,
  traceIdForNextChatRequest,
  askUserQuestionPayloadFromEvent,
  type ChatMessage,
  type StreamEvent,
} from "./streaming_chat"

function readerFromLines(lines: string[]) {
  let i = 0
  const enc = new TextEncoder()
  return {
    getReader: () => ({
      read: () => {
        if (i >= lines.length) {
          return Promise.resolve({ done: true, value: undefined })
        }
        const line = lines[i]
        i += 1
        return Promise.resolve({ done: false, value: enc.encode(line) })
      },
    }),
  }
}

describe("traceIdForNextChatRequest", () => {
  it("returns the latest assistant traceId", () => {
    const msgs: ChatMessage[] = [
      { id: "1", role: "user", content: "hi" },
      { id: "2", role: "assistant", parts: [], traceId: "a" },
      { id: "3", role: "user", content: "again" },
      { id: "4", role: "assistant", parts: [], traceId: "b" },
    ]
    expect(traceIdForNextChatRequest(msgs)).toBe("b")
  })

  it("returns undefined when no assistant has traceId", () => {
    const msgs: ChatMessage[] = [
      { id: "1", role: "user", content: "hi" },
      { id: "2", role: "assistant", parts: [] },
    ]
    expect(traceIdForNextChatRequest(msgs)).toBeUndefined()
  })
})

describe("streamChat", () => {
  it("includes trace_id in POST body when traceId option is set", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: {
        getReader: () =>
          ({
            read: () => Promise.resolve({ done: true, value: undefined }),
          }) as ReadableStreamDefaultReader<Uint8Array>,
      },
    })
    vi.stubGlobal("fetch", fetchMock)

    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      traceId: "tid-1",
      onAssistantMessage: () => {},
      onFinish: () => {},
      onError: () => {},
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(init.body as string)).toEqual({
      messages: [{ role: "user", content: "hi" }],
      trace_id: "tid-1",
    })

    vi.unstubAllGlobals()
  })

  it("posts execute-tools when tool-calls-pending is received", async () => {
    const lines = [
      'data: {"type":"kiln_chat_trace","trace_id":"trace-1"}\n\n',
      'data: {"type":"tool-calls-pending","items":[{"toolCallId":"tc1","toolName":"t","input":{},"requiresApproval":true}]}\n\n',
    ]
    let i = 0
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string, init?: RequestInit) => {
        if (url.endsWith("/execute-tools")) {
          expect(init?.method).toBe("POST")
          const body = JSON.parse(init?.body as string) as {
            trace_id: string
            tool_calls: Array<{ toolCallId: string; requiresApproval: boolean }>
            decisions: Record<string, boolean>
          }
          expect(body.trace_id).toBe("trace-1")
          expect(body.tool_calls).toHaveLength(1)
          expect(body.tool_calls[0].toolCallId).toBe("tc1")
          expect(body.decisions).toEqual({ tc1: true })
          return Promise.resolve({
            ok: true,
            body: {
              getReader: () => ({
                read: () => Promise.resolve({ done: true, value: undefined }),
              }),
            },
          })
        }
        return Promise.resolve({
          ok: true,
          body: {
            getReader: () => ({
              read: () => {
                if (i >= lines.length) {
                  return Promise.resolve({ done: true, value: undefined })
                }
                const enc = new TextEncoder()
                const line = lines[i]
                i += 1
                return Promise.resolve({
                  done: false,
                  value: enc.encode(line),
                })
              },
            }),
          },
        })
      })
    vi.stubGlobal("fetch", fetchMock)

    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      onAssistantMessage: () => {},
      onToolCallsPending: async (payload) => {
        const out: Record<string, boolean> = {}
        for (const it of payload.items) {
          if (it.requiresApproval) {
            out[it.toolCallId] = true
          }
        }
        return out
      },
      onFinish: () => {},
      onError: () => {},
    })

    expect(fetchMock.mock.calls.length).toBe(2)
    expect(chatExecuteToolsUrl("https://example.test/api/chat")).toBe(
      "https://example.test/api/chat/execute-tools",
    )

    vi.unstubAllGlobals()
  })

  it("calls onInlineError with code when response has chat_client_version_too_old", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      text: () =>
        Promise.resolve(
          JSON.stringify({
            message: {
              message: "Update required",
              code: CHAT_CLIENT_VERSION_TOO_OLD,
            },
          }),
        ),
    })
    vi.stubGlobal("fetch", fetchMock)

    const inlineErrorSpy = vi.fn()

    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      onAssistantMessage: () => {},
      onInlineError: inlineErrorSpy,
      onFinish: () => {},
      onError: () => {},
    })

    expect(inlineErrorSpy).toHaveBeenCalledOnce()
    expect(inlineErrorSpy.mock.calls[0][2]).toBe(CHAT_CLIENT_VERSION_TOO_OLD)

    vi.unstubAllGlobals()
  })

  it("calls onError for non-version error responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      text: () => Promise.resolve("server error"),
    })
    vi.stubGlobal("fetch", fetchMock)

    const errorSpy = vi.fn()
    const inlineErrorSpy = vi.fn()

    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      onAssistantMessage: () => {},
      onInlineError: inlineErrorSpy,
      onFinish: () => {},
      onError: errorSpy,
    })

    expect(errorSpy).toHaveBeenCalledOnce()
    expect(inlineErrorSpy).not.toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})

describe("askUserQuestionPayloadFromEvent", () => {
  it("parses question + valid suggestions, defaulting missing explanations", () => {
    const payload = askUserQuestionPayloadFromEvent({
      type: "ask-user-question",
      trace_id: "t1",
      // Real app-server wire shape: snake_case ``tool_call_id``
      // (stream_session._format_ask_user_question_sse).
      tool_call_id: "tc1",
      question: "Which one?",
      suggested_answers: [
        { answer: "A", explanation: "because A" },
        { answer: "B" },
      ],
    } as StreamEvent)
    // The parsed toolCallId must equal the wire ``tool_call_id``.
    expect(payload.toolCallId).toBe("tc1")
    expect(payload).toEqual({
      traceId: "t1",
      toolCallId: "tc1",
      question: "Which one?",
      suggestedAnswers: [
        { answer: "A", explanation: "because A" },
        { answer: "B", explanation: "" },
      ],
    })
  })

  it("drops malformed suggestions and caps to 5", () => {
    const raw = Array.from({ length: 8 }, (_, i) => ({ answer: `A${i}` }))
    // Inject a malformed entry that must be skipped.
    const withBad = [{ explanation: "no answer" }, ...raw] as Array<{
      answer?: unknown
    }>
    const payload = askUserQuestionPayloadFromEvent({
      type: "ask-user-question",
      tool_call_id: "tc",
      question: "q",
      suggested_answers: withBad,
    } as StreamEvent)
    expect(payload.suggestedAnswers).toHaveLength(5)
    expect(payload.suggestedAnswers[0].answer).toBe("A0")
  })
})

describe("streamChat ask-user-question", () => {
  it("renders the question card part, fires onAskUserQuestion, and ends the stream", async () => {
    const lines = [
      'data: {"type":"kiln_chat_trace","trace_id":"trace-q"}\n\n',
      // Real app-server wire shape: snake_case ``tool_call_id``.
      'data: {"type":"ask-user-question","trace_id":"trace-q","tool_call_id":"tc1","question":"Pick?","suggested_answers":[{"answer":"A","explanation":"e"}]}\n\n',
      // Anything after the question must NOT be processed (stream ends).
      'data: {"type":"text-start","id":"x"}\n\n',
      'data: {"type":"text-delta","delta":"should not render"}\n\n',
    ]
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, body: readerFromLines(lines) })
    vi.stubGlobal("fetch", fetchMock)

    const askSpy = vi.fn()
    const finishSpy = vi.fn()
    let lastParts: ChatMessage["parts"] = []

    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      onAssistantMessage: (update) => {
        const draft: ChatMessage = { id: "a", role: "assistant", parts: [] }
        update(draft)
        lastParts = draft.parts
      },
      onAskUserQuestion: askSpy,
      onFinish: finishSpy,
      onError: () => {},
    })

    expect(askSpy).toHaveBeenCalledTimes(1)
    // The parsed toolCallId must equal the wire ``tool_call_id``.
    expect(askSpy.mock.calls[0][0].toolCallId).toBe("tc1")
    expect(askSpy.mock.calls[0][0]).toMatchObject({
      toolCallId: "tc1",
      question: "Pick?",
      suggestedAnswers: [{ answer: "A", explanation: "e" }],
    })
    // The card part was rendered, carrying the wire tool call id.
    const askPart = lastParts?.find((p) => p.type === "ask-user-question")
    expect(askPart).toBeTruthy()
    expect((askPart as { toolCallId?: string } | undefined)?.toolCallId).toBe(
      "tc1",
    )
    // The stream ended on the question: the trailing text was never rendered.
    const textPart = lastParts?.find((p) => p.type === "text")
    expect(textPart).toBeUndefined()
    expect(finishSpy).toHaveBeenCalledTimes(1)

    vi.unstubAllGlobals()
  })
})

describe("resumePendingToolCalls (graceful-stop handoff)", () => {
  it("approves surfaced tools and POSTs execute-tools, streaming the continuation", async () => {
    // The continuation stream the backend returns after execute-tools.
    const contLines = [
      'data: {"type":"text-start","id":"x"}\n\n',
      'data: {"type":"text-delta","delta":"resumed"}\n\n',
    ]
    let i = 0
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string, init?: RequestInit) => {
        expect(url).toBe("https://example.test/api/chat/execute-tools")
        expect(init?.method).toBe("POST")
        const body = JSON.parse(init?.body as string) as {
          trace_id: string
          tool_calls: Array<{ toolCallId: string }>
          decisions: Record<string, boolean>
        }
        expect(body.trace_id).toBe("trace-stop")
        expect(body.tool_calls[0].toolCallId).toBe("tc1")
        expect(body.decisions).toEqual({ tc1: true })
        return Promise.resolve({
          ok: true,
          body: {
            getReader: () => ({
              read: () => {
                if (i >= contLines.length) {
                  return Promise.resolve({ done: true, value: undefined })
                }
                const enc = new TextEncoder()
                const line = contLines[i]
                i += 1
                return Promise.resolve({ done: false, value: enc.encode(line) })
              },
            }),
          },
        })
      })
    vi.stubGlobal("fetch", fetchMock)

    const approvalSpy = vi.fn(async () => ({ tc1: true }))
    const finishSpy = vi.fn()
    let assistantText = ""

    await resumePendingToolCalls({
      apiUrl: "https://example.test/api/chat",
      traceId: "trace-stop",
      items: [
        {
          toolCallId: "tc1",
          toolName: "call_kiln_api",
          input: { path: "/x" },
          requiresApproval: true,
        },
      ],
      onToolCallsPending: approvalSpy,
      onAssistantMessage: (update) => {
        const draft: ChatMessage = { id: "a", role: "assistant", parts: [] }
        update(draft)
        const part = draft.parts?.[0]
        if (part && part.type === "text") assistantText = part.text
      },
      onFinish: finishSpy,
      onError: () => {},
    })

    // The existing approval gate was used (no parallel approval UI).
    expect(approvalSpy).toHaveBeenCalledOnce()
    // The continuation streamed into the conversation.
    expect(assistantText).toBe("resumed")
    expect(finishSpy).toHaveBeenCalledOnce()

    vi.unstubAllGlobals()
  })
})

import { describe, expect, it, vi } from "vitest"
import { CHAT_CLIENT_VERSION_TOO_OLD } from "$lib/error_codes"
import {
  streamChat,
  chatExecuteToolsUrl,
  traceIdForNextChatRequest,
  type ChatMessage,
} from "./streaming_chat"

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

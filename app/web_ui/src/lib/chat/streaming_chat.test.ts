import { describe, expect, it, vi } from "vitest"
import {
  streamChat,
  chatToolApprovalUrl,
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

  it("posts tool approval when tool-approval-required is received", async () => {
    const lines = [
      'data: {"type":"tool-approval-required","approvalBatchId":"batch-1","items":[{"toolCallId":"tc1","toolName":"t"}]}\n\n',
      'data: {"type":"finish"}\n\n',
    ]
    let i = 0
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string, init?: RequestInit) => {
        if (url.endsWith("/tool-approval")) {
          expect(init?.method).toBe("POST")
          expect(JSON.parse(init?.body as string)).toEqual({
            approval_batch_id: "batch-1",
            decisions: { tc1: true },
          })
          return Promise.resolve(
            new Response(JSON.stringify({ ok: true }), { status: 200 }),
          )
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

    const decisions: Record<string, boolean> = {}
    await streamChat({
      apiUrl: "https://example.test/api/chat",
      messages: [{ id: "u1", role: "user", content: "hi" }],
      onAssistantMessage: () => {},
      onToolApprovalRequired: async (payload) => {
        for (const it of payload.items) {
          decisions[it.toolCallId] = true
        }
        return decisions
      },
      onFinish: () => {},
      onError: () => {},
    })

    expect(fetchMock.mock.calls.length).toBe(2)
    expect(chatToolApprovalUrl("https://example.test/api/chat")).toBe(
      "https://example.test/api/chat/tool-approval",
    )

    vi.unstubAllGlobals()
  })
})

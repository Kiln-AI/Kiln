import { describe, expect, it, vi } from "vitest"
import {
  streamChat,
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
})

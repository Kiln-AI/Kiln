import { describe, it, expect, vi, afterEach } from "vitest"
import { stream_sse } from "./sse_stream"
import { createKilnError } from "./error_handlers"

/** A Response whose body streams the given chunks, one read at a time. */
function streaming_response(
  chunks: string[],
  init: ResponseInit = {},
): Response {
  const encoder = new TextEncoder()
  let index = 0
  const body = {
    getReader: () => ({
      read: async () => {
        if (index >= chunks.length) {
          return { done: true, value: undefined }
        }
        return { done: false, value: encoder.encode(chunks[index++]) }
      },
    }),
  }
  return { ok: true, status: 200, body, ...init } as unknown as Response
}

function error_response(status: number, body: unknown): Response {
  return {
    ok: false,
    status,
    json: async () => body,
  } as unknown as Response
}

function mock_fetch(response: Response | (() => Promise<Response>)) {
  const fn = vi.fn(
    typeof response === "function" ? response : async () => response,
  )
  vi.stubGlobal("fetch", fn)
  return fn
}

/** Let the helper's promise chain drain. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("stream_sse", () => {
  it("dispatches each event's data payload in order", async () => {
    mock_fetch(
      streaming_response(['data: {"progress":1}\n\n', "data: complete\n\n"]),
    )
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual(['{"progress":1}', "complete"])
  })

  it("reassembles an event split across chunk boundaries", async () => {
    mock_fetch(streaming_response(['data: {"prog', 'ress":1}\n\n']))
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual(['{"progress":1}'])
  })

  it("dispatches several events arriving in a single chunk", async () => {
    mock_fetch(
      streaming_response(['data: {"progress":1}\n\ndata: {"progress":2}\n\n']),
    )
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual(['{"progress":1}', '{"progress":2}'])
  })

  it("joins a multi-line data field into one payload, as the SSE spec requires", async () => {
    mock_fetch(streaming_response(["data: first\ndata: second\n\n"]))
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual(["first\nsecond"])
  })

  it("ignores non-data lines in an event", async () => {
    mock_fetch(
      streaming_response([": keepalive\nevent: progress\ndata: one\n\n"]),
    )
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual(["one"])
  })

  it("does not dispatch a partial event still waiting for its terminator", async () => {
    mock_fetch(streaming_response(['data: {"progress":1}']))
    const messages: string[] = []

    stream_sse("/run", {
      on_message: (d) => messages.push(d),
      on_error: () => {},
    })
    await settle()

    expect(messages).toEqual([])
  })

  it("reports a body that ends without completing, rather than going quiet", async () => {
    // Silence here would pin the caller in its "running" state with no error shown and
    // no retry offered — a worse failure than the one this reader replaced.
    mock_fetch(streaming_response(['data: {"progress":1}\n\n']))
    let error: unknown = null

    stream_sse("/run", {
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain("without completing")
  })

  it("names the caller's subject in the early-end message", async () => {
    // Pins the interpolation: a hardcoded noun would pass the assertion above, which is
    // why this asserts the whole composed sentence rather than a fragment of it.
    mock_fetch(streaming_response(['data: {"progress":1}\n\n']))
    let error: unknown = null

    stream_sse("/run", {
      subject: "eval stream",
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain(
      "The eval stream ended without completing.",
    )
  })

  it("falls back to a neutral subject, since the module is domain-neutral", async () => {
    mock_fetch(streaming_response(['data: {"progress":1}\n\n']))
    let error: unknown = null

    stream_sse("/run", {
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain(
      "The stream ended without completing.",
    )
  })

  it("reports nothing when the caller closed on the terminal message", async () => {
    // The happy path: `data: complete` handled, close() called, stream ends. The
    // end-of-body error above must not fire here.
    mock_fetch(streaming_response(["data: complete\n\n"]))
    let error: unknown = null

    const stream = stream_sse("/run", {
      on_message: () => stream.close(),
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(error).toBeNull()
  })

  it("surfaces the server's message for a refusal, not a bare event", async () => {
    // The whole point of not using EventSource: a 422 body reaches the user.
    mock_fetch(
      error_response(422, {
        message: "Eval 'e1' has no golden set. Add one to compare judges.",
      }),
    )
    let error: unknown = null

    stream_sse("/run", {
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain("has no golden set")
  })

  it("falls back to the status when the error body isn't JSON", async () => {
    mock_fetch({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error("not json")
      },
    } as unknown as Response)
    let error: unknown = null

    stream_sse("/run", {
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain("502")
  })

  it("reports a transport failure", async () => {
    mock_fetch(async () => {
      throw new Error("network down")
    })
    let error: unknown = null

    stream_sse("/run", {
      on_message: () => {},
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(createKilnError(error).getMessage()).toContain("network down")
  })

  it("stops dispatching after close(), and reports nothing", async () => {
    mock_fetch(
      streaming_response(["data: one\n\n", "data: two\n\n", "data: three\n\n"]),
    )
    const messages: string[] = []
    let error: unknown = null

    const stream = stream_sse("/run", {
      on_message: (d) => {
        messages.push(d)
        if (d === "one") {
          stream.close()
        }
      },
      on_error: (e) => {
        error = e
      },
    })
    await settle()

    expect(messages).toEqual(["one"])
    expect(error).toBeNull()
  })

  it("aborts the request when a handler throws, so the server stops working", async () => {
    let seen_signal: AbortSignal | undefined
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        seen_signal = init.signal ?? undefined
        return streaming_response(["data: one\n\n"])
      }),
    )

    stream_sse("/run", {
      on_message: () => {
        throw new Error("handler blew up")
      },
      on_error: () => {},
    })
    await settle()

    expect(seen_signal?.aborted).toBe(true)
  })

  it("aborts the request on close, so the server sees the disconnect", async () => {
    let seen_signal: AbortSignal | undefined
    const fetch_mock = vi.fn(async (_url: string, init: RequestInit) => {
      seen_signal = init.signal ?? undefined
      return streaming_response([])
    })
    vi.stubGlobal("fetch", fetch_mock)

    const stream = stream_sse("/run", {
      on_message: () => {},
      on_error: () => {},
    })
    stream.close()
    await settle()

    expect(seen_signal?.aborted).toBe(true)
  })
})

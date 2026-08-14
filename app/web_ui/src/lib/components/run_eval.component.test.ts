// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

// The reason run_eval.svelte reads its stream with `stream_sse` instead of an
// `EventSource` is that these endpoints refuse up front with a 4xx naming the reason —
// no golden set, no such split, and now a V1 judge on an eval whose test split isn't
// backed by dataset runs. `EventSource` cannot read the status or body of a non-200, so
// every one of those reasons arrived as "Unknown error". This file covers the last mile:
// that the refusal's own words reach the screen.
//
// `fetch` is stubbed rather than `$lib/utils/sse_stream` mocked, so the real module and
// the real wiring (subject, on_message, on_error) are what run. sse_stream.test.ts covers
// the module in isolation; the wiring is what was untested.

vi.mock("posthog-js", () => ({
  default: { capture: vi.fn() },
}))

vi.mock("$lib/api_client", () => ({
  base_url: "http://localhost:8757",
}))

const RunEval = (await import("./run_eval.svelte")).default

// jsdom doesn't implement HTMLDialogElement.showModal/close; emulate them so the `open`
// property reflects the real show()/close() calls the component makes.
beforeEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).showModal = function (
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "")
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(HTMLDialogElement.prototype as any).close = function (
    this: HTMLDialogElement,
  ) {
    this.removeAttribute("open")
  }
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

/** Let stream_sse's promise chain drain. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

/** A non-2xx response shaped the way kiln_server's HTTPException handler writes one. */
function refusal(status: number, message: string): Response {
  return {
    ok: false,
    status,
    json: async () => ({ message }),
  } as unknown as Response
}

/** A 200 SSE body that streams the given chunks, one read at a time. */
function streaming_response(chunks: string[]): Response {
  const encoder = new TextEncoder()
  let index = 0
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => {
          if (index >= chunks.length) {
            return { done: true, value: undefined }
          }
          return { done: false, value: encoder.encode(chunks[index++]) }
        },
      }),
    },
  } as unknown as Response
}

function render_run_eval(props: Record<string, unknown> = {}) {
  return render(RunEval, {
    props: {
      eval_type: "run_config",
      project_id: "proj1",
      task_id: "task1",
      eval_id: "eval1",
      current_eval_config_id: "config1",
      run_all: true,
      ...props,
    },
  })
}

/** Click the launch button, then the "Run Eval" button inside the confirm dialog. */
async function start_run(container: HTMLElement) {
  const launch = Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("Run All Evals"),
  )
  expect(launch).toBeDefined()
  await fireEvent.click(launch!)
  await tick()

  const confirm = Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === "Run Eval",
  )
  expect(confirm).toBeDefined()
  await fireEvent.click(confirm!)
  await tick()
  await settle()
  await tick()
}

/** The page's copy is wrapped across source lines, so compare on collapsed whitespace. */
function visible_text(container: HTMLElement): string {
  return (container.textContent ?? "").replace(/\s+/g, " ").trim()
}

// The wording the API refuses a V1 judge with, verbatim from
// `judge_needs_dataset_runs_message` in app/desktop/studio_server/eval_api.py.
const V1_JUDGE_REFUSAL =
  "Eval 'My Eval' uses our new eval dataset format, which the 'g_eval' judge type " +
  "can't score. Choose a judge type that supports the new format."

describe("run_eval — an up-front refusal reaches the user", () => {
  it("shows the server's own 400 message, not a generic error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => refusal(400, V1_JUDGE_REFUSAL)),
    )
    const { container } = render_run_eval()

    await start_run(container)

    // The whole point of the migration: the reason survives the trip to the screen.
    expect(visible_text(container)).toContain(V1_JUDGE_REFUSAL)
    expect(visible_text(container)).not.toContain("Unknown error")
  })

  it("shows the 422 message when the eval has no golden set", async () => {
    // The other up-front refusal on these endpoints (require_golden_set_or_422). Both
    // statuses go down the same path, so this pins that the path isn't 400-specific.
    const message = "Eval 'My Eval' has no golden set configured."
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => refusal(422, message)),
    )
    const { container } = render_run_eval()

    await start_run(container)

    expect(visible_text(container)).toContain(message)
  })

  it("requests the run endpoint the props name, and asks for an event stream", async () => {
    const fetch_mock = vi.fn(async () => refusal(400, V1_JUDGE_REFUSAL))
    vi.stubGlobal("fetch", fetch_mock)
    const { container } = render_run_eval()

    await start_run(container)

    expect(fetch_mock).toHaveBeenCalledTimes(1)
    const [url, init] = fetch_mock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ]
    expect(url).toContain(
      "/api/projects/proj1/tasks/task1/evals/eval1/eval_config/config1/run_comparison",
    )
    expect(url).toContain("all_run_configs=true")
    expect((init.headers as Record<string, string>).Accept).toBe(
      "text/event-stream",
    )
  })

  it("KNOWN ROUGH EDGE: a refusal is headlined as a completed eval", async () => {
    // The refusal path sets eval_state to "complete_with_errors", which is also the
    // state a run that started and then failed some jobs lands in. So the dialog
    // headlines "Eval Complete with Errors" and the button reads "Eval Errors", for a
    // run that never started — the only accurate part of the screen is the message
    // underneath. Asserted as-is to document what ships today, NOT because it is right.
    // Reported rather than fixed: this is a test-only change.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => refusal(400, V1_JUDGE_REFUSAL)),
    )
    const { container } = render_run_eval()

    await start_run(container)

    expect(visible_text(container)).toContain("Eval Complete with Errors")
    expect(visible_text(container)).toContain("Eval Errors")
  })

  it("notifies the caller that the run finished, so its data reloads", async () => {
    // on_run_complete fires on the refusal path too. That is deliberate: the callers use
    // it to re-enable their UI, and a refusal that left them waiting forever would be
    // worse than one that reloads unchanged data.
    const on_run_complete = vi.fn()
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => refusal(400, V1_JUDGE_REFUSAL)),
    )
    const { container } = render_run_eval({ on_run_complete })

    await start_run(container)

    expect(on_run_complete).toHaveBeenCalledTimes(1)
  })
})

describe("run_eval — a stream that does run", () => {
  it("reports progress and then completion", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streaming_response([
          'data: {"progress":1,"total":4,"errors":0}\n\n',
          'data: {"progress":3,"total":4,"errors":1}\n\n',
          "data: complete\n\n",
        ]),
      ),
    )
    const on_run_complete = vi.fn()
    const { container } = render_run_eval({ on_run_complete })

    await start_run(container)

    // 3 done + 1 errored of 4, and one error — the counts come from the last progress
    // event, so a reader that dropped events would show 1 of 4 here.
    expect(visible_text(container)).toContain("4 of 4")
    expect(visible_text(container)).toContain("1 error")
    // Errors seen during the run, so the terminal state is the with-errors one.
    expect(visible_text(container)).toContain("Eval Complete with Errors")
    expect(on_run_complete).toHaveBeenCalledTimes(1)
  })

  it("reports a clean completion when no job errored", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streaming_response([
          'data: {"progress":2,"total":2,"errors":0}\n\n',
          "data: complete\n\n",
        ]),
      ),
    )
    const { container } = render_run_eval()

    await start_run(container)

    const text = visible_text(container)
    expect(text).toContain("Eval Complete")
    expect(text).not.toContain("Eval Complete with Errors")
  })

  it("names the eval stream when the body ends without completing", async () => {
    // stream_sse composes this one message itself and takes the noun from `subject`, so
    // this is the assertion that the caller passes a domain-specific one rather than
    // letting an eval user read about a bare "stream".
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        streaming_response(['data: {"progress":1,"total":4,"errors":0}\n\n']),
      ),
    )
    const { container } = render_run_eval()

    await start_run(container)

    expect(visible_text(container)).toContain(
      "The eval stream ended without completing.",
    )
  })
})

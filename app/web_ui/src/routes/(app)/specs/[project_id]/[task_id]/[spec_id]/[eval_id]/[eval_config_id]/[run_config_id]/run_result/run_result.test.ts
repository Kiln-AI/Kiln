// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, setResultsResponse, mockReplaceState } =
  vi.hoisted(() => {
    const pageValue = {
      params: {
        project_id: "proj1",
        task_id: "task1",
        spec_id: "spec1",
        eval_id: "eval1",
        eval_config_id: "ec1",
        run_config_id: "rc1",
      },
      url: new URL("http://localhost/specs/proj1/task1/spec1/eval1/ec1/rc1"),
    }
    const mockPage = {
      subscribe(fn: (value: typeof pageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    }

    let results_response: Record<string, unknown> = {}
    const setResultsResponse = (v: Record<string, unknown>) => {
      results_response = v
    }
    const mockClientGET = vi.fn().mockImplementation(() => {
      return Promise.resolve({ data: results_response, error: null })
    })

    // SvelteKit's replaceState moves the browser URL; jsdom's history does the same.
    const mockReplaceState = vi.fn((url: string) => {
      window.history.replaceState(null, "", url)
    })

    return {
      mockPage,
      mockClientGET,
      setResultsResponse,
      mockReplaceState,
    }
  })

// Svelte 4 onMount callbacks do not run under jsdom/vitest. The page's callback
// opens a bound dialog, so run it once the mount has finished.
vi.mock("svelte", async (importOriginal) => {
  const actual = await importOriginal<typeof import("svelte")>()
  return {
    ...actual,
    // @testing-library/svelte probes this Svelte 5 only export to pick a mount strategy.
    mount: undefined,
    onMount: (fn: () => unknown) => queueMicrotask(() => void fn()),
  }
})

vi.mock("$app/stores", () => ({
  page: mockPage,
}))

vi.mock("$app/navigation", () => ({
  replaceState: mockReplaceState,
}))

vi.mock("$lib/api_client", () => ({
  client: {
    GET: mockClientGET,
  },
}))

vi.mock("$lib/stores", () => ({
  model_info: {
    subscribe: (fn: (v: null) => void) => {
      fn(null)
      return () => {}
    },
  },
  load_model_info: vi.fn(),
  model_name: () => "Model",
  provider_name_from_id: () => "Provider",
  prompt_name_from_id: () => "Prompt",
  load_available_models: vi.fn(),
  get_task_composite_id: (project_id: string, task_id: string) =>
    `${project_id}:${task_id}`,
}))

vi.mock("$lib/stores/prompts_store", () => ({
  prompts_by_task_composite_id: {
    subscribe: (fn: (v: Record<string, unknown>) => void) => {
      fn({})
      return () => {}
    },
  },
  load_task_prompts: vi.fn(),
}))

vi.mock("$lib/agent", () => ({
  agentInfo: { set: vi.fn() },
}))

// Stub heavy UI components with real .svelte stubs
vi.mock("../../../../../../../../app_page.svelte", async () => {
  const Stub = await import("../../../__tests__/app_page_stub.svelte")
  return { default: Stub.default }
})

// jsdom does not implement <dialog>.showModal(), which the real Dialog calls on mount.
vi.mock("$lib/ui/dialog.svelte", async () => {
  const Stub = await import("./__tests__/dialog_stub.svelte")
  return { default: Stub.default }
})

vi.mock("$lib/ui/trace/chat_trace.svelte", async () => {
  const Stub = await import("./__tests__/chat_trace_stub.svelte")
  return { default: Stub.default }
})

// Dynamic import after all mocks
const RunResultPage = (await import("./+page.svelte")).default

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const base_response = {
  eval: {
    id: "eval1",
    name: "Test Eval",
    eval_set_filter_id: "tag::eval_set",
    eval_configs_filter_id: "tag::golden",
    output_scores: [{ name: "accuracy", type: "five_star" }],
  },
  eval_config: {
    id: "ec1",
    name: "Judge",
    config_type: "g_eval",
    model_name: "gpt-4",
    model_provider: "openai",
    properties: {},
  },
  run_config: {
    id: "rc1",
    name: "Run Config",
    run_config_properties: {
      type: "kiln_agent",
      model_name: "gpt-4",
      model_provider_name: "openai",
      prompt_id: "simple_prompt_builder",
    },
  },
}

async function render_page(
  results: Array<Record<string, unknown>>,
  response_overrides: Record<string, unknown> = {},
): Promise<HTMLElement> {
  setResultsResponse({ ...base_response, ...response_overrides, results })
  const { container } = render(RunResultPage)
  await tick()
  await new Promise((r) => setTimeout(r, 0))
  await tick()
  return container
}

// The placeholder copy is wrapped across source lines, so compare on collapsed
// whitespace.
function visible_text(container: HTMLElement): string {
  return (container.textContent ?? "").replace(/\s+/g, " ").trim()
}

const PLACEHOLDER =
  "Trace unavailable. It may have been deleted or not included in an import."

function result_row(overrides: Record<string, unknown>) {
  return {
    input: null,
    output: null,
    task_run_trace: null,
    task_run_usage: null,
    ...overrides,
  }
}

// A multi-turn conversation: two user turns and two assistant replies.
const conversation = [
  { role: "system", content: "You are a helpful assistant." },
  { role: "user", content: "What is the capital of France?" },
  { role: "assistant", content: "Paris." },
  { role: "user", content: "And Spain?" },
  { role: "assistant", content: "Madrid." },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

afterEach(() => {
  cleanup()
  window.history.replaceState(null, "", "/")
  mockReplaceState.mockClear()
})

describe("run result page — missing trace placeholder", () => {
  it("renders the placeholder in the output cell for a dangling scored_run_id", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er1",
          scored_run_id: "gone_run",
          scores: {},
          intermediate_outputs: null,
        },
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain(PLACEHOLDER)
  })

  it("renders the placeholder beside a filled input when only the trace is gone", async () => {
    // The server fills input from the dataset item when the trace can't supply it,
    // so a dangling pointer usually arrives with input set and output null. The
    // placeholder must still appear where the output would have been.
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er4",
          scored_run_id: "gone_run",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the question from the dataset item",
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain(PLACEHOLDER)
    expect(text).toContain("the question from the dataset item")
  })

  it("renders input and output, not the placeholder, when the trace resolved", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er2",
          scored_run_id: "tr2",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the input",
        output: "the output",
      }),
    ])

    const text = visible_text(container)
    expect(text).not.toContain(PLACEHOLDER)
    expect(text).toContain("the input")
    expect(text).toContain("the output")
  })

  it("does not use the placeholder for records that never pointed at a trace", async () => {
    // A run skipped before generation has no scored_run_id; nothing was deleted, so
    // "trace unavailable" would be the wrong statement.
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er3",
          scores: {},
          intermediate_outputs: null,
          skipped_reason: "missing_reference_key",
        },
      }),
    ])

    expect(visible_text(container)).not.toContain(PLACEHOLDER)
  })
})

describe("run result page — a renderable trace gates the conversation view", () => {
  // A row that carries a renderable conversation alongside its flat input and
  // output, so each test can vary only what the row's trace holds.
  function traced_row(eval_run_extra: Record<string, unknown> = {}) {
    return traced_row_with(
      "er_trace",
      JSON.stringify(conversation),
      eval_run_extra,
    )
  }

  function traced_row_with(
    id: string,
    task_run_trace: string,
    eval_run_extra: Record<string, unknown> = {},
  ) {
    return result_row({
      eval_run: {
        id,
        scored_run_id: "tr1",
        scores: {},
        intermediate_outputs: null,
        ...eval_run_extra,
      },
      input: "the input",
      output: "the output",
      task_run_trace,
    })
  }

  it("reads a single exchange as a conversation too", async () => {
    // A single-turn run records a transcript, so its one exchange gets the
    // same treatment a longer conversation does.
    const container = await render_page([
      traced_row_with(
        "er_one_exchange",
        JSON.stringify([
          { role: "user", content: "What is the capital of France?" },
          { role: "assistant", content: "Paris." },
        ]),
      ),
    ])

    const text = visible_text(container)
    expect(text).toContain("What is the capital of France?")
    expect(text).toContain("View Full Trace")
    expect(text).not.toContain("Input: the input")
    expect(container.querySelector("thead th")?.textContent?.trim()).toBe(
      "Interaction",
    )
  })

  it("keeps the Input & Output view for a row with no trace", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er_no_trace",
          scored_run_id: "gone_run",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the question from the dataset item",
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain("the question from the dataset item")
    expect(text).toContain(PLACEHOLDER)
    expect(text).not.toContain("View Full Trace")
    // Nothing on the page reads as a conversation, so the header must not
    // promise one either: the whole page is what it has always been.
    expect(container.querySelector("thead th")?.textContent?.trim()).toBe(
      "Input & Output",
    )
  })

  it("leaves a trace-less row flat on a page that has conversations", async () => {
    // The conversation view is per row, not per page: one row earning it must
    // not pull the rows beside it out of the Input & Output view.
    const container = await render_page([
      traced_row(),
      result_row({
        eval_run: {
          id: "er_flat",
          scored_run_id: null,
          scores: {},
          intermediate_outputs: null,
        },
        input: "the flat input",
        output: "the flat output",
      }),
    ])

    expect(container.querySelector("thead th")?.textContent?.trim()).toBe(
      "Interaction",
    )
    const rows = container.querySelectorAll("tbody tr")
    expect(rows.length).toBe(2)
    const flat_row = visible_text(rows[1] as HTMLElement)
    expect(flat_row).toContain("Input: the flat input")
    expect(flat_row).toContain("Output: the flat output")
    expect(flat_row).not.toContain("View Full Trace")
  })

  it("renders a compact row for a row with a renderable trace", async () => {
    const container = await render_page([
      traced_row({ reference_answer: "Paris and Madrid." }),
    ])

    const text = visible_text(container)
    expect(text).toContain("What is the capital of France?")
    expect(text).toContain("Reference Answer: Paris and Madrid.")
    // The flat blob is replaced, not merely supplemented.
    expect(text).not.toContain("Input: the input")
    expect(text).not.toContain("the output")
    expect(
      container.querySelector("button.text-primary")?.textContent?.trim(),
    ).toBe("View Full Trace")

    // The cell reads in the flat view's order: input, then reference answer.
    const cell_blocks = Array.from(
      container.querySelector("tbody td > div")?.children ?? [],
    ).map((el) => (el.textContent ?? "").replace(/\s+/g, " ").trim())
    expect(cell_blocks).toEqual([
      "What is the capital of France?",
      "Reference Answer: Paris and Madrid.",
      "View Full Trace",
    ])
  })

  it("renders a compact row for a conversation with a well-formed tool call", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er_tool_call",
          scored_run_id: "tr_tool",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the input",
        output: "the output",
        task_run_trace: JSON.stringify([
          { role: "user", content: "What is the weather in Paris?" },
          {
            role: "assistant",
            content: null,
            tool_calls: [
              {
                id: "call_1",
                type: "function",
                function: {
                  name: "get_weather",
                  arguments: '{"city":"Paris"}',
                },
              },
            ],
          },
          {
            role: "tool",
            tool_call_id: "call_1",
            content: '{"output":"Sunny"}',
          },
          { role: "assistant", content: "It is sunny in Paris." },
        ]),
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain("What is the weather in Paris?")
    expect(text).toContain("View Full Trace")
    expect(text).not.toContain("Input: the input")
  })

  it("opens the trace dialog with the row's conversation", async () => {
    const container = await render_page([traced_row()])

    // Nothing of the conversation is on screen until the link opens the dialog.
    expect(
      container.querySelector("[data-testid='chat-trace-stub']"),
    ).toBeNull()
    expect(visible_text(container)).not.toContain("assistant: Madrid.")

    const link = container.querySelector("button.text-primary")
    await fireEvent.click(link!)
    await tick()

    const chat = container.querySelector("[data-testid='chat-trace-stub']")
    expect(chat).not.toBeNull()
    const chat_text = visible_text(chat as HTMLElement)
    expect(chat_text).toContain("user: What is the capital of France?")
    expect(chat_text).toContain("assistant: Madrid.")
  })

  it("falls back to the row input when the conversation has no plain-text user message", async () => {
    const container = await render_page([
      result_row({
        eval_run: {
          id: "er_no_user_text",
          scored_run_id: "tr2",
          scores: {},
          intermediate_outputs: null,
        },
        input: "the dataset input",
        output: "the output",
        task_run_trace: JSON.stringify([
          { role: "user", content: null },
          { role: "assistant", content: "Madrid." },
        ]),
      }),
    ])

    const text = visible_text(container)
    expect(text).toContain("View Full Trace")
    // The input fills the preview slot, so it appears without the flat label.
    expect(text).toContain("the dataset input")
    expect(text).not.toContain("Input: the dataset input")
  })

  it("falls back to the flat view for traces it cannot render as a conversation", async () => {
    const unrenderable: Array<[string, string]> = [
      ["not valid json", "not json at all"],
      ["not an array", JSON.stringify({ messages: conversation })],
      ["array of primitives", JSON.stringify(["hi", "there"])],
      [
        "content part list",
        JSON.stringify([
          { role: "user", content: [{ type: "text", text: "hi" }] },
        ]),
      ],
      [
        "no user or assistant message",
        JSON.stringify([{ role: "system", content: "only a system prompt" }]),
      ],
      [
        // ChatTrace reads tool_call.function.name unguarded, so this threw
        // mid-render and left an empty dialog wedged open.
        "tool call with no function",
        JSON.stringify([
          { role: "user", content: "hi" },
          { role: "assistant", content: "ok", tool_calls: [{ id: "x" }] },
        ]),
      ],
      [
        "tool calls that are not a list",
        JSON.stringify([
          { role: "user", content: "hi" },
          { role: "assistant", content: "ok", tool_calls: "not a list" },
        ]),
      ],
      [
        // ChatTrace has no branch for this role, so it would speak as the
        // assistant.
        "unknown role",
        JSON.stringify([
          { role: "user", content: "hi" },
          { role: "function", content: "legacy function message" },
        ]),
      ],
    ]

    const container = await render_page(
      unrenderable.map(([label, raw], i) =>
        result_row({
          eval_run: {
            id: `er_bad_${i}`,
            scored_run_id: `tr_bad_${i}`,
            scores: {},
            intermediate_outputs: null,
          },
          input: `input for ${label}`,
          output: `output for ${label}`,
          task_run_trace: raw,
        }),
      ),
    )

    expect(container.querySelectorAll("tbody tr").length).toBe(
      unrenderable.length,
    )
    const text = visible_text(container)
    for (const [label] of unrenderable) {
      expect(text).toContain(`Input: input for ${label}`)
      expect(text).toContain(`Output: output for ${label}`)
    }
    expect(text).not.toContain("View Full Trace")
  })
})

describe("run result page — dialog deep links", () => {
  function traced_row(id: string, first_question: string) {
    return result_row({
      eval_run: {
        id,
        scored_run_id: `tr_${id}`,
        scores: {},
        intermediate_outputs: { reasoning: `reasoning for ${id}` },
      },
      input: "the input",
      output: "the output",
      task_run_trace: JSON.stringify([
        { role: "user", content: first_question },
        { role: "assistant", content: `answer for ${id}` },
      ]),
    })
  }

  const rows = [
    traced_row("er_first", "First question?"),
    traced_row("er_second", "Second question?"),
  ]

  function dialog_stub(container: HTMLElement, title: string): HTMLElement {
    const stub = container.querySelector<HTMLElement>(
      `[data-testid='dialog-stub'][data-title='${title}']`,
    )
    expect(stub).not.toBeNull()
    return stub!
  }

  const peek = (container: HTMLElement) =>
    dialog_stub(container, "Are you sure you want to peek?")
  const trace = (container: HTMLElement) => dialog_stub(container, "Trace")
  const reasoning = (container: HTMLElement) =>
    dialog_stub(container, "Judge Reasoning")

  // A hash change in the same document, as when a link to this page is pasted
  // into the address bar. jsdom fires hashchange on a later task.
  async function follow_link(hash: string) {
    window.location.hash = hash
    await new Promise((r) => setTimeout(r, 0))
    await tick()
  }

  async function close_dialog(dialog: HTMLElement) {
    await fireEvent.click(
      dialog.querySelector("[data-testid='dialog-stub-close']")!,
    )
    await tick()
  }

  it("writes the row's trace link into the URL when its trace opens", async () => {
    const container = await render_page(rows)

    const links = container.querySelectorAll("button.text-primary")
    await fireEvent.click(links[1])
    await tick()

    expect(window.location.hash).toBe("#trace-er_second")
    expect(visible_text(trace(container))).toContain(
      "assistant: answer for er_second",
    )
  })

  it("clears the trace link from the URL when the trace closes", async () => {
    window.history.replaceState(null, "", "/run_result?view=all")
    const container = await render_page(rows)
    await fireEvent.click(container.querySelector("button.text-primary")!)
    await tick()
    expect(window.location.hash).toBe("#trace-er_first")

    const close = trace(container).querySelector(
      "[data-testid='dialog-stub-close']",
    )
    await fireEvent.click(close!)
    await tick()

    expect(window.location.hash).toBe("")
    expect(window.location.pathname + window.location.search).toBe(
      "/run_result?view=all",
    )
  })

  it("opens the linked trace on load, under the peek warning", async () => {
    window.history.replaceState(null, "", "/#trace-er_second")
    const container = await render_page(rows)

    expect(trace(container).dataset.open).toBe("true")
    expect(visible_text(trace(container))).toContain(
      "assistant: answer for er_second",
    )
    expect(peek(container).dataset.open).toBe("true")
    // The dialog opened last is the one on top.
    expect(Number(peek(container).dataset.openedAt)).toBeGreaterThan(
      Number(trace(container).dataset.openedAt),
    )
    expect(window.location.hash).toBe("#trace-er_second")
    expect(mockReplaceState).not.toHaveBeenCalled()
  })

  it("holds the peek warning until the linked trace can open beneath it", async () => {
    window.history.replaceState(null, "", "/#trace-er_first")
    let resolve_results: (value: unknown) => void = () => {}
    mockClientGET.mockImplementationOnce(
      () => new Promise((resolve) => (resolve_results = resolve)),
    )
    const { container } = render(RunResultPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))

    expect(peek(container).dataset.open).toBe("false")

    resolve_results({ data: { ...base_response, results: rows }, error: null })
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(trace(container).dataset.open).toBe("true")
    expect(peek(container).dataset.open).toBe("true")
  })

  it("shows only the peek warning when the linked row is not in the results", async () => {
    window.history.replaceState(null, "", "/#trace-er_missing")
    const container = await render_page(rows)

    expect(peek(container).dataset.open).toBe("true")
    expect(trace(container).dataset.open).toBe("false")
  })

  it("shows the peek warning on mount when the URL has no trace link", async () => {
    const container = await render_page(rows)

    expect(peek(container).dataset.open).toBe("true")
    expect(trace(container).dataset.open).toBe("false")
  })

  it("opens the trace a link on this page points to, without the peek warning again", async () => {
    const container = await render_page(rows)
    await close_dialog(peek(container))

    await follow_link("#trace-er_second")

    expect(trace(container).dataset.open).toBe("true")
    expect(visible_text(trace(container))).toContain(
      "assistant: answer for er_second",
    )
    expect(peek(container).dataset.open).toBe("false")
  })

  it("switches the open trace when a link points to another row", async () => {
    const container = await render_page(rows)
    await close_dialog(peek(container))
    await fireEvent.click(container.querySelector("button.text-primary")!)
    await tick()
    expect(visible_text(trace(container))).toContain("answer for er_first")

    await follow_link("#trace-er_second")

    expect(trace(container).dataset.open).toBe("true")
    expect(visible_text(trace(container))).toContain(
      "assistant: answer for er_second",
    )
    expect(visible_text(trace(container))).not.toContain("answer for er_first")
  })

  it.each([
    ["a row that is not in the results", "#trace-er_missing"],
    ["no dialog", "#other"],
  ])(
    "closes the trace when a link on this page points to %s",
    async (_, hash) => {
      const container = await render_page(rows)
      await close_dialog(peek(container))
      await follow_link("#trace-er_first")
      expect(trace(container).dataset.open).toBe("true")

      await follow_link(hash)

      expect(trace(container).dataset.open).toBe("false")
    },
  )

  it("holds a followed link until the peek warning closes", async () => {
    const container = await render_page(rows)

    await follow_link("#trace-er_second")
    expect(peek(container).dataset.open).toBe("true")
    expect(trace(container).dataset.open).toBe("false")

    await close_dialog(peek(container))
    await tick()

    expect(trace(container).dataset.open).toBe("true")
    expect(visible_text(trace(container))).toContain(
      "assistant: answer for er_second",
    )
  })

  it("still shows the peek warning when the link leaves the URL before the results load", async () => {
    window.history.replaceState(null, "", "/#trace-er_first")
    let resolve_results: (value: unknown) => void = () => {}
    mockClientGET.mockImplementationOnce(
      () => new Promise((resolve) => (resolve_results = resolve)),
    )
    const { container } = render(RunResultPage)
    await tick()
    await new Promise((r) => setTimeout(r, 0))

    await follow_link("#other")
    resolve_results({ data: { ...base_response, results: rows }, error: null })
    await new Promise((r) => setTimeout(r, 0))
    await tick()

    expect(peek(container).dataset.open).toBe("true")
    expect(trace(container).dataset.open).toBe("false")
  })

  describe("judge reasoning", () => {
    const llm_judge = {
      eval_config: {
        id: "ec1",
        name: "Judge",
        config_type: "v2",
        properties: {
          type: "llm_judge",
          model_name: "gpt-4",
          model_provider: "openai",
          g_eval: false,
        },
      },
    }

    function view_reasoning_buttons(container: HTMLElement) {
      return [...container.querySelectorAll("button")].filter((button) =>
        button.textContent?.includes("View reasoning"),
      )
    }

    it("writes the row's reasoning link into the URL when its reasoning opens", async () => {
      const container = await render_page(rows, llm_judge)

      await fireEvent.click(view_reasoning_buttons(container)[1])
      await tick()

      expect(window.location.hash).toBe("#reasoning-er_second")
      expect(reasoning(container).dataset.open).toBe("true")
      expect(visible_text(reasoning(container))).toContain(
        "reasoning for er_second",
      )
      // The page's dialog stands in for each row's own one.
      expect(
        container.querySelectorAll("[data-title='Judge Reasoning']"),
      ).toHaveLength(1)
    })

    it("clears the reasoning link from the URL when the reasoning closes", async () => {
      window.history.replaceState(null, "", "/run_result?view=all")
      const container = await render_page(rows, llm_judge)
      await fireEvent.click(view_reasoning_buttons(container)[0])
      await tick()
      expect(window.location.hash).toBe("#reasoning-er_first")

      await close_dialog(reasoning(container))

      expect(window.location.hash).toBe("")
      expect(window.location.pathname + window.location.search).toBe(
        "/run_result?view=all",
      )
    })

    it("opens the linked reasoning on load, under the peek warning", async () => {
      window.history.replaceState(null, "", "/#reasoning-er_second")
      const container = await render_page(rows, llm_judge)

      expect(reasoning(container).dataset.open).toBe("true")
      expect(visible_text(reasoning(container))).toContain(
        "reasoning for er_second",
      )
      expect(trace(container).dataset.open).toBe("false")
      expect(peek(container).dataset.open).toBe("true")
      expect(Number(peek(container).dataset.openedAt)).toBeGreaterThan(
        Number(reasoning(container).dataset.openedAt),
      )
      expect(mockReplaceState).not.toHaveBeenCalled()
    })

    it("swaps between the trace and the reasoning as links on this page point to each", async () => {
      const container = await render_page(rows, llm_judge)
      await close_dialog(peek(container))
      await fireEvent.click(container.querySelector("button.text-primary")!)
      await tick()

      await follow_link("#reasoning-er_second")

      expect(trace(container).dataset.open).toBe("false")
      expect(reasoning(container).dataset.open).toBe("true")
      expect(visible_text(reasoning(container))).toContain(
        "reasoning for er_second",
      )
      expect(window.location.hash).toBe("#reasoning-er_second")

      await follow_link("#trace-er_first")

      expect(reasoning(container).dataset.open).toBe("false")
      expect(trace(container).dataset.open).toBe("true")
      expect(window.location.hash).toBe("#trace-er_first")
    })

    it("shows only the peek warning when the linked row has no reasoning", async () => {
      window.history.replaceState(null, "", "/#reasoning-er_plain")
      const plain_row = result_row({
        eval_run: {
          id: "er_plain",
          scored_run_id: "tr_er_plain",
          scores: {},
          intermediate_outputs: null,
        },
      })
      const container = await render_page([...rows, plain_row], llm_judge)

      expect(peek(container).dataset.open).toBe("true")
      expect(reasoning(container).dataset.open).toBe("false")
    })
  })
})

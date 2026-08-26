// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent } from "@testing-library/svelte"
import { tick } from "svelte"

// ---------------------------------------------------------------------------
// Module-level mocks — must come before the dynamic page import
// ---------------------------------------------------------------------------

const { mockPage, mockClientGET, mockLoadTask, setResultsResponse } =
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

    return {
      mockPage,
      mockClientGET,
      mockLoadTask: vi.fn(),
      setResultsResponse,
    }
  })

vi.mock("$app/stores", () => ({
  page: mockPage,
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
  load_task: mockLoadTask,
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

const single_turn_task = {
  id: "task1",
  name: "Test Task",
  turn_mode: "single_turn",
}
const multi_turn_task = { ...single_turn_task, turn_mode: "multiturn" }

// Renders with whatever load_task the caller already configured.
async function render_configured(
  results: Array<Record<string, unknown>>,
): Promise<HTMLElement> {
  setResultsResponse({ ...base_response, results })
  const { container } = render(RunResultPage)
  await tick()
  await new Promise((r) => setTimeout(r, 0))
  await tick()
  return container
}

async function render_page(
  results: Array<Record<string, unknown>>,
  task: Record<string, unknown> = single_turn_task,
): Promise<HTMLElement> {
  mockLoadTask.mockResolvedValue(task)
  return render_configured(results)
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

// A plain multi-turn conversation: two user turns and two assistant replies.
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

beforeEach(() => {
  mockLoadTask.mockReset()
})

afterEach(() => {
  cleanup()
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

describe("run result page — turn mode gates the conversation view", () => {
  // A row that carries a renderable conversation alongside its flat input and
  // output, so each test can vary only the turn mode.
  function traced_row(eval_run_extra: Record<string, unknown> = {}) {
    return result_row({
      eval_run: {
        id: "er_trace",
        scored_run_id: "tr1",
        scores: {},
        intermediate_outputs: null,
        ...eval_run_extra,
      },
      input: "the input",
      output: "the output",
      task_run_trace: JSON.stringify(conversation),
    })
  }

  it("keeps the Input & Output view on a single-turn task whose rows carry traces", async () => {
    const container = await render_page([traced_row()], single_turn_task)

    const text = visible_text(container)
    expect(text).toContain("Input: the input")
    expect(text).toContain("Output: the output")
    expect(text).not.toContain("View Full Trace")
    expect(
      container.querySelector("[data-testid='chat-trace-stub']"),
    ).toBeNull()
  })

  it("keeps the Input & Output view when the task cannot be loaded", async () => {
    // An unknown turn mode must degrade to today's view, not fail the page.
    mockLoadTask.mockRejectedValue(new Error("task gone"))
    const container = await render_configured([traced_row()])

    const text = visible_text(container)
    expect(text).toContain("Input: the input")
    expect(text).toContain("Output: the output")
    expect(text).not.toContain("View Full Trace")
  })

  it("keeps the Input & Output view for a multi-turn row with no trace", async () => {
    const container = await render_page(
      [
        result_row({
          eval_run: {
            id: "er_no_trace",
            scored_run_id: "gone_run",
            scores: {},
            intermediate_outputs: null,
          },
          input: "the question from the dataset item",
        }),
      ],
      multi_turn_task,
    )

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

  it("renders a compact row for a multi-turn row with a renderable trace", async () => {
    const container = await render_page(
      [traced_row({ reference_answer: "Paris and Madrid." })],
      multi_turn_task,
    )

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
    const container = await render_page(
      [
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
      ],
      multi_turn_task,
    )

    const text = visible_text(container)
    expect(text).toContain("What is the weather in Paris?")
    expect(text).toContain("View Full Trace")
    expect(text).not.toContain("Input: the input")
  })

  it("opens the trace dialog with the row's conversation", async () => {
    const container = await render_page([traced_row()], multi_turn_task)

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
    const container = await render_page(
      [
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
      ],
      multi_turn_task,
    )

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
      multi_turn_task,
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

  it("labels the first column by turn mode", async () => {
    const single_turn = await render_page([traced_row()], single_turn_task)
    expect(single_turn.querySelector("thead th")?.textContent?.trim()).toBe(
      "Input & Output",
    )
    cleanup()

    const multi_turn = await render_page([traced_row()], multi_turn_task)
    expect(multi_turn.querySelector("thead th")?.textContent?.trim()).toBe(
      "Interaction",
    )
  })
})

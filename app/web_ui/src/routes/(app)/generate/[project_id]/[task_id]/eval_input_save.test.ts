import { beforeEach, describe, expect, it, vi } from "vitest"

const mockClientPOST = vi.fn()

vi.mock("$lib/api_client", () => ({
  client: { POST: mockClientPOST },
}))

const {
  eval_input_tags,
  eval_input_text,
  is_eval_input_split,
  save_eval_input,
} = await import("./eval_input_save")

describe("eval_input_text", () => {
  it("passes a plain input through", () => {
    expect(eval_input_text("What is your return window?")).toBe(
      "What is your return window?",
    )
  })

  it("serializes a structured input, the shape the builder mints", () => {
    expect(eval_input_text({ order_id: 7, urgent: true })).toBe(
      '{"order_id":7,"urgent":true}',
    )
  })
})

describe("eval_input_tags", () => {
  it("tags the case the way the run endpoints tag a generated run", () => {
    // data_gen_api builds ["synthetic", "synthetic_session_<id>", <split>] for a run. A
    // case saved to the eval's inputs instead has to be findable the same way.
    expect(eval_input_tags("test_my_spec", "12345")).toEqual([
      "synthetic",
      "synthetic_session_12345",
      "test_my_spec",
    ])
  })

  it("drops the session tag when there is no session", () => {
    expect(eval_input_tags("test_my_spec", null)).toEqual([
      "synthetic",
      "test_my_spec",
    ])
  })
})

describe("save_eval_input", () => {
  beforeEach(() => {
    mockClientPOST.mockReset()
  })

  it("posts the case alone, with no output", async () => {
    mockClientPOST.mockResolvedValue({ data: { id: "ei_1" }, error: null })

    const id = await save_eval_input(
      "proj",
      "task",
      "What is your return window?",
      "test_my_spec",
      "12345",
    )

    expect(id).toBe("ei_1")
    expect(mockClientPOST).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks/{task_id}/eval_inputs",
      {
        params: { path: { project_id: "proj", task_id: "task" } },
        body: {
          data: {
            type: "single_turn",
            user_message: { text: "What is your return window?" },
          },
          tags: ["synthetic", "synthetic_session_12345", "test_my_spec"],
        },
      },
    )
  })

  it("serializes a structured input", async () => {
    mockClientPOST.mockResolvedValue({ data: { id: "ei_2" }, error: null })

    await save_eval_input("proj", "task", { order_id: 7 }, "train_x", null)

    const body = mockClientPOST.mock.calls[0][1].body
    expect(body.data.user_message.text).toBe('{"order_id":7}')
    expect(body.tags).toEqual(["synthetic", "train_x"])
  })

  it("throws the API's error rather than reporting a save", async () => {
    mockClientPOST.mockResolvedValue({ data: null, error: { message: "boom" } })

    await expect(
      save_eval_input("proj", "task", "input", "test_x", null),
    ).rejects.toEqual({ message: "boom" })
  })

  it("throws when the save returns no id", async () => {
    mockClientPOST.mockResolvedValue({ data: {}, error: null })

    await expect(
      save_eval_input("proj", "task", "input", "test_x", null),
    ).rejects.toThrow("no id returned")
  })
})

describe("is_eval_input_split", () => {
  it("routes a tag the eval names as eval-input backed to the eval's inputs", () => {
    expect(is_eval_input_split("test_x", ["test_x", "train_x"])).toBe(true)
  })

  it("routes a tag the eval doesn't name to the dataset", () => {
    // A split the user invented in the tag editor is a dataset tag: no eval reads it, so an
    // eval input under it would sit in a store nothing opens.
    expect(is_eval_input_split("slice_a", ["test_x"])).toBe(false)
  })

  it("routes a case with no split to the dataset", () => {
    expect(is_eval_input_split(null, ["test_x"])).toBe(false)
    expect(is_eval_input_split(undefined, ["test_x"])).toBe(false)
  })

  it("routes everything to the dataset when the eval names no eval-input splits", () => {
    // Every legacy eval, and the fine-tuning flow, which carries no eval at all.
    expect(is_eval_input_split("test_x", [])).toBe(false)
    expect(is_eval_input_split("test_x", null)).toBe(false)
    expect(is_eval_input_split("test_x", undefined)).toBe(false)
  })
})

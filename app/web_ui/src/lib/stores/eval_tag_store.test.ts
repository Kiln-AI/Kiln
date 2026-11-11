import { describe, it, expect, vi, beforeEach } from "vitest"
import { get } from "svelte/store"
import type { Eval, Spec } from "$lib/types"

const { mock_get } = vi.hoisted(() => ({ mock_get: vi.fn() }))
vi.mock("$lib/api_client", () => ({ client: { GET: mock_get } }))

import {
  count_eval_tags,
  eval_tag_store_by_task_id,
  increment_eval_tag,
  invalidate_eval_tags,
  load_eval_tags,
  set_eval_tags,
} from "./eval_tag_store"

function make_spec(overrides: Partial<Spec> = {}): Spec {
  return {
    id: "spec1",
    name: "Spec One",
    definition: "definition",
    properties: { spec_type: "toxicity" },
    priority: 1,
    status: "active",
    tags: [],
    eval_id: "eval1",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as Spec
}

function make_eval(overrides: Partial<Eval> = {}): Eval {
  return {
    id: "eval1",
    name: "Eval One",
    eval_set_filter_id: "tag::eval_set",
    eval_configs_filter_id: "tag::golden",
    output_scores: [{ name: "score", type: "pass_fail" }],
    priority: 1,
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as Eval
}

describe("count_eval_tags", () => {
  it("counts how many evals use each tag", () => {
    const specs = [
      make_spec({ id: "s1", eval_id: "e1", tags: ["billing", "v3"] }),
      make_spec({ id: "s2", eval_id: "e2", tags: ["v3"] }),
    ]
    const evals = [make_eval({ id: "e1" }), make_eval({ id: "e2" })]

    expect(count_eval_tags(specs, evals)).toEqual({ billing: 1, v3: 2 })
  })

  it("leaves out evals archived on the eval", () => {
    const specs = [
      make_spec({ id: "s1", eval_id: "e1", tags: ["kept"] }),
      make_spec({ id: "s2", eval_id: "e2", tags: ["retired"] }),
    ]
    const evals = [
      make_eval({ id: "e1" }),
      make_eval({ id: "e2", status: "archived" }),
    ]

    expect(count_eval_tags(specs, evals)).toEqual({ kept: 1 })
  })

  it("leaves out evals archived on the spec when the eval has no status", () => {
    const specs = [
      make_spec({
        id: "s1",
        eval_id: "e1",
        status: "archived",
        tags: ["retired"],
      }),
    ]
    const evals = [make_eval({ id: "e1", status: undefined })]

    expect(count_eval_tags(specs, evals)).toEqual({})
  })
})

describe("eval tag store", () => {
  beforeEach(() => {
    eval_tag_store_by_task_id.set({})
    mock_get.mockReset()
  })

  function answer_with(specs: Spec[], evals: Eval[]) {
    mock_get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/specs")
          ? { data: specs, error: undefined }
          : { data: { evals, load_error_count: 0 }, error: undefined },
      ),
    )
  }

  it("loads counts once per task and reuses them", async () => {
    answer_with(
      [make_spec({ id: "s1", eval_id: "e1", tags: ["v3"] })],
      [make_eval({ id: "e1" })],
    )

    expect(await load_eval_tags("p1", "t1")).toEqual({ v3: 1 })
    expect(await load_eval_tags("p1", "t1")).toEqual({ v3: 1 })
    expect(mock_get).toHaveBeenCalledTimes(2)
  })

  it("fetches again after the task's counts are invalidated", async () => {
    answer_with([make_spec({ tags: ["old"] })], [make_eval()])
    await load_eval_tags("p1", "t1")

    invalidate_eval_tags("t1")
    answer_with([make_spec({ tags: ["new"] })], [make_eval()])

    expect(await load_eval_tags("p1", "t1")).toEqual({ new: 1 })
  })

  it("returns no suggestions when a request fails", async () => {
    mock_get.mockResolvedValue({ data: undefined, error: { detail: "boom" } })

    expect(await load_eval_tags("p1", "t1")).toEqual({})
    expect(get(eval_tag_store_by_task_id)["t1"]).toBeUndefined()
  })

  it("uses counts the page set without fetching", async () => {
    set_eval_tags("t1", [make_spec({ tags: ["seeded"] })], [make_eval()])

    expect(await load_eval_tags("p1", "t1")).toEqual({ seeded: 1 })
    expect(mock_get).not.toHaveBeenCalled()
  })

  it("increments a loaded task's count and ignores an unloaded task", () => {
    set_eval_tags("t1", [make_spec({ tags: ["v3"] })], [make_eval()])

    increment_eval_tag("t1", "v3")
    increment_eval_tag("t1", "fresh")
    increment_eval_tag("t2", "ignored")

    expect(get(eval_tag_store_by_task_id)).toEqual({
      t1: { v3: 2, fresh: 1 },
    })
  })
})

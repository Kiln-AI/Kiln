// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tag_store_by_task_id } from "$lib/stores/tag_store"
import { eval_tag_store_by_task_id } from "$lib/stores/eval_tag_store"

vi.mock("$lib/stores/tag_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/tag_store")>()),
  load_tags: vi.fn(),
}))
vi.mock("$lib/stores/eval_tag_store", async (importOriginal) => ({
  ...(await importOriginal<typeof import("$lib/stores/eval_tag_store")>()),
  load_eval_tags: vi.fn(),
}))

import TagDropdown from "./tag_dropdown.svelte"

function suggestions(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("datalist option")).map(
    (option) => option.getAttribute("value") ?? "",
  )
}

afterEach(() => {
  cleanup()
  tag_store_by_task_id.set({})
  eval_tag_store_by_task_id.set({})
})

describe("TagDropdown eval suggestions", () => {
  it("suggests the task's eval tags, most used first, without task run tags", () => {
    tag_store_by_task_id.set({ t1: { manual_run: 9 } })
    eval_tag_store_by_task_id.set({ t1: { billing: 1, v3: 4 } })

    const { container } = render(TagDropdown, {
      project_id: "p1",
      task_id: "t1",
      example_tag_set: "eval",
    })

    expect(suggestions(container)).toEqual(["v3", "billing"])
  })

  it("suggests task run tags for task runs", () => {
    tag_store_by_task_id.set({ t1: { manual_run: 9 } })
    eval_tag_store_by_task_id.set({ t1: { v3: 4 } })

    const { container } = render(TagDropdown, {
      project_id: "p1",
      task_id: "t1",
      example_tag_set: "task_run",
    })

    expect(suggestions(container)[0]).toBe("manual_run")
    expect(suggestions(container)).not.toContain("v3")
  })
})

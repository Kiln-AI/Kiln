import { describe, it, expect } from "vitest"
import { get } from "svelte/store"
import { jobs_dialog } from "./jobs_dialog"

describe("jobs_dialog", () => {
  it("bumps the open signal each time open() is called", () => {
    const before = get(jobs_dialog.open_signal)
    jobs_dialog.open()
    const afterOne = get(jobs_dialog.open_signal)
    expect(afterOne).toBe(before + 1)
    jobs_dialog.open()
    expect(get(jobs_dialog.open_signal)).toBe(before + 2)
  })
})

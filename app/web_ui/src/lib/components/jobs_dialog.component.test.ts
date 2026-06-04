// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import { writable } from "svelte/store"
import type { JobRecord } from "$lib/stores/jobs_api"
import { jobs_dialog } from "$lib/stores/jobs_dialog"

// The dialog hosts JobsTable, which subscribes to the job stream. Mock the
// stores/api so the table renders an inert empty state.
const jobs = writable<JobRecord[]>([])
const synced = writable(true)
const connection = writable<"idle" | "connecting" | "open" | "errored">("open")

vi.mock("$lib/stores/jobs_store", () => ({
  jobs,
  synced,
  connection,
}))

vi.mock("$lib/stores/jobs_api", () => ({
  pause_job: vi.fn().mockResolvedValue(undefined),
  resume_job: vi.fn().mockResolvedValue(undefined),
  cancel_job: vi.fn().mockResolvedValue(undefined),
  delete_job: vi.fn().mockResolvedValue(undefined),
  get_job_errors: vi.fn().mockResolvedValue([]),
  get_job_result: vi.fn().mockResolvedValue({}),
}))

const JobsDialog = (await import("./jobs_dialog.svelte")).default

// jsdom doesn't implement HTMLDialogElement.showModal/close; emulate them so
// the `open` property reflects the real show()/close() calls the component makes.
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
  jobs.set([])
  synced.set(true)
  connection.set("open")
})

afterEach(() => {
  cleanup()
})

function jobsDialogEl(container: HTMLElement): HTMLDialogElement {
  // The first dialog in the tree is the Jobs dialog (the errors/result
  // sub-dialogs live inside JobsTable and follow it).
  const el = container.querySelector("dialog")
  expect(el).not.toBeNull()
  return el as HTMLDialogElement
}

describe("JobsDialog open signal", () => {
  it("stays closed on mount even if the signal has already advanced", async () => {
    // Advance the module-level signal before the component mounts.
    jobs_dialog.open()
    jobs_dialog.open()

    const { container } = render(JobsDialog)
    await tick()

    expect(jobsDialogEl(container).open).toBe(false)
  })

  it("opens when jobs_dialog.open() is called", async () => {
    const { container } = render(JobsDialog)
    await tick()
    expect(jobsDialogEl(container).open).toBe(false)

    jobs_dialog.open()
    await tick()

    expect(jobsDialogEl(container).open).toBe(true)
  })

  it("re-opens after being closed", async () => {
    const { container } = render(JobsDialog)
    await tick()

    jobs_dialog.open()
    await tick()
    expect(jobsDialogEl(container).open).toBe(true)

    // Close it the way the user would (the dialog's own close()).
    jobsDialogEl(container).close()
    expect(jobsDialogEl(container).open).toBe(false)

    jobs_dialog.open()
    await tick()
    expect(jobsDialogEl(container).open).toBe(true)
  })

  it("does not reopen on an unrelated reactive update", async () => {
    const { container } = render(JobsDialog)
    await tick()
    expect(jobsDialogEl(container).open).toBe(false)

    // Mutate unrelated reactive inputs the dialog/table read; none of these
    // touch the open signal, so the dialog must remain closed.
    jobs.set([])
    synced.set(true)
    connection.set("open")
    await tick()

    expect(jobsDialogEl(container).open).toBe(false)
  })
})

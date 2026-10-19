// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"

const { mock_get, mock_patch } = vi.hoisted(() => ({
  mock_get: vi.fn(),
  mock_patch: vi.fn(),
}))

vi.mock("$lib/api_client", () => ({
  client: { GET: mock_get, PATCH: mock_patch },
  base_url: "http://localhost:8757",
}))

const ScoreDisplayNameDialog = (
  await import("./score_display_name_dialog.svelte")
).default

function eval_with_scores(
  display_name: string | null,
): Record<string, unknown> {
  return {
    id: "eval1",
    output_scores: [
      { name: "Tone Check", display_name, type: "pass_fail" },
      { name: "accuracy", display_name: null, type: "five_star" },
    ],
  }
}

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
  vi.clearAllMocks()
})

async function open_dialog(display_name: string | null) {
  mock_get.mockResolvedValue({ data: eval_with_scores(display_name) })
  const saved = vi.fn()
  const { component, container } = render(ScoreDisplayNameDialog, {
    props: { project_id: "p1", task_id: "t1" },
  })
  component.$on("saved", (e: CustomEvent) => saved(e.detail))
  await component.show("eval1", "tone_check")
  const input = await waitFor(() => {
    const el = container.querySelector(
      "#score_display_name",
    ) as HTMLInputElement | null
    expect(el).not.toBeNull()
    return el as HTMLInputElement
  })
  return { container, input, saved }
}

async function submit(container: HTMLElement) {
  const button = container.querySelector(
    'button[type="submit"]',
  ) as HTMLButtonElement
  await fireEvent.click(button)
}

describe("ScoreDisplayNameDialog", () => {
  it("pre-fills the current display name", async () => {
    const { input } = await open_dialog("Politeness")
    expect(input.value).toBe("Politeness")
    expect(mock_get).toHaveBeenCalledWith(
      "/api/projects/{project_id}/tasks/{task_id}/evals/{eval_id}",
      {
        params: { path: { project_id: "p1", task_id: "t1", eval_id: "eval1" } },
      },
    )
  })

  it("pre-fills the score name when no display name is set", async () => {
    const { input } = await open_dialog(null)
    expect(input.value).toBe("Tone Check")
  })

  it("saves only this score's display name and reports the new label", async () => {
    mock_patch.mockResolvedValue({ data: eval_with_scores("Politeness") })
    const { container, input, saved } = await open_dialog(null)

    await fireEvent.input(input, { target: { value: "  Politeness " } })
    await submit(container)

    await waitFor(() => expect(saved).toHaveBeenCalledTimes(1))
    expect(mock_patch.mock.calls[0][1].body).toEqual({
      output_score_display_names: { tone_check: "Politeness" },
    })
    expect(saved).toHaveBeenCalledWith({
      eval_id: "eval1",
      score_key: "tone_check",
      display_name: "Politeness",
    })
  })

  it("requires a name", async () => {
    const { container, input, saved } = await open_dialog("Politeness")

    await fireEvent.input(input, { target: { value: "" } })
    await submit(container)

    await waitFor(() => expect(container.textContent).toMatch(/required/i))
    expect(mock_patch).not.toHaveBeenCalled()
    expect(saved).not.toHaveBeenCalled()
  })

  it("shows the server error and doesn't report a save when the PATCH fails", async () => {
    mock_patch.mockResolvedValue({
      error: { message: "output_scores must have unique display names" },
    })
    const { container, input, saved } = await open_dialog(null)

    await fireEvent.input(input, { target: { value: "accuracy" } })
    await submit(container)

    await waitFor(() =>
      expect(container.textContent).toContain("unique display names"),
    )
    expect(saved).not.toHaveBeenCalled()
  })

  it("ignores a load from an earlier opening that finishes last", async () => {
    let resolve_first: (value: unknown) => void = () => {}
    mock_get
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolve_first = resolve)),
      )
      .mockResolvedValueOnce({ data: eval_with_scores(null) })
    const { component, container } = render(ScoreDisplayNameDialog, {
      props: { project_id: "p1", task_id: "t1" },
    })

    const first = component.show("eval0", "tone_check")
    await component.show("eval1", "accuracy")
    resolve_first({
      data: {
        id: "eval0",
        output_scores: [
          { name: "Tone Check", display_name: "Stale", type: "pass_fail" },
        ],
      },
    })
    await first

    const input = container.querySelector(
      "#score_display_name",
    ) as HTMLInputElement
    await waitFor(() => expect(input.value).toBe("accuracy"))
  })
})

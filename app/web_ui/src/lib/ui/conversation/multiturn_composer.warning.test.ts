// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import type { SendMultiturnResult } from "$lib/services/multiturn_send"

const send_multiturn = vi.fn<[], Promise<SendMultiturnResult>>()
vi.mock("$lib/services/multiturn_send", () => ({
  send_multiturn: () => send_multiturn(),
}))

const MultiturnComposer = (await import("./multiturn_composer.svelte")).default

afterEach(() => {
  cleanup()
  send_multiturn.mockReset()
})

const SESSION_ENDED =
  "The OpenEnv session for this conversation ended. Start a new conversation to keep using this OpenEnv."

async function send_and_fail(
  status: number,
  warning_error_statuses: number[],
): Promise<HTMLElement> {
  send_multiturn.mockResolvedValue({
    ok: false,
    error: { message: SESSION_ENDED },
    status,
  })
  const { container, getByRole } = render(MultiturnComposer, {
    props: {
      project_id: "p1",
      task_id: "t1",
      parent_task_run_id: "leaf-42",
      on_success: vi.fn(),
      warning_error_statuses,
    },
  })
  await fireEvent.click(getByRole("button", { name: /Send/ }))
  await waitFor(() => expect(send_multiturn).toHaveBeenCalledOnce())
  await waitFor(() =>
    expect(container.textContent).toContain("OpenEnv session"),
  )
  return container
}

describe("MultiturnComposer warning_error_statuses", () => {
  it("shows a listed status as an error Warning above the form", async () => {
    const container = await send_and_fail(409, [409])
    const warning = container.querySelector(
      '[data-testid="multiturn-composer-warning"]',
    )
    expect(warning?.textContent).toContain(SESSION_ENDED)
    expect(container.querySelector(".text-center.text-error")).toBeNull()
  })

  it("keeps other statuses in the form's error line", async () => {
    const container = await send_and_fail(400, [409])
    expect(
      container.querySelector('[data-testid="multiturn-composer-warning"]'),
    ).toBeNull()
    expect(
      container.querySelector(".text-center.text-error")?.textContent,
    ).toContain(SESSION_ENDED)
  })

  it("keeps every status in the error line by default", async () => {
    const container = await send_and_fail(409, [])
    expect(
      container.querySelector('[data-testid="multiturn-composer-warning"]'),
    ).toBeNull()
    expect(
      container.querySelector(".text-center.text-error")?.textContent,
    ).toContain(SESSION_ENDED)
  })
})

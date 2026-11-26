// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte"
import { KilnError } from "$lib/utils/error_handlers"
import type { TrustCodeState } from "./trust_code"

const { mockPage, mockLoad, mockGrant } = vi.hoisted(() => {
  const pageValue = {
    params: { project_id: "p1" },
    url: new URL("http://localhost/settings/trust_code/p1"),
  }
  return {
    mockPage: {
      subscribe(fn: (v: typeof pageValue) => void) {
        fn(pageValue)
        return () => {}
      },
    },
    mockLoad: vi.fn<[string], Promise<TrustCodeState>>(),
    mockGrant: vi.fn<[string], Promise<KilnError | null>>(),
  }
})

vi.mock("$app/stores", () => ({ page: mockPage }))
vi.mock("$app/navigation", () => ({ goto: vi.fn() }))
vi.mock("$lib/agent", () => ({ agentInfo: { set: vi.fn() } }))
vi.mock("./trust_code", () => ({
  load_trust_code: mockLoad,
  grant_code_trust: mockGrant,
}))

import Page from "./+page.svelte"

const RETURN_MESSAGE =
  "Return to your agent and tell it code trust was granted."

beforeEach(() => {
  mockLoad.mockReset()
  mockGrant.mockReset()
})

afterEach(() => {
  cleanup()
})

describe("Trust Code page", () => {
  it("asks the trust question for the project", async () => {
    mockLoad.mockResolvedValue({
      kind: "question",
      project_name: "Support Bot",
    })
    const { findByTestId, getByText } = render(Page)
    await findByTestId("trust-code-grant")
    expect(mockLoad).toHaveBeenCalledWith("p1")
    getByText('Trust the code in Project "Support Bot"?')
    getByText(/This project wants to run Python code on your machine/)
    getByText("Never paste code from a stranger or the internet.")
  })

  it("grants trust and tells the user to return to the agent", async () => {
    mockLoad.mockResolvedValue({
      kind: "question",
      project_name: "Support Bot",
    })
    mockGrant.mockResolvedValue(null)
    const { findByTestId, queryByTestId } = render(Page)
    await fireEvent.click(await findByTestId("trust-code-grant"))
    expect(mockGrant).toHaveBeenCalledWith("p1")
    expect((await findByTestId("trust-code-granted")).textContent).toContain(
      RETURN_MESSAGE,
    )
    expect(queryByTestId("trust-code-grant")).toBeNull()
  })

  it("keeps the question and shows the error when the grant fails", async () => {
    mockLoad.mockResolvedValue({
      kind: "question",
      project_name: "Support Bot",
    })
    mockGrant.mockResolvedValue(new KilnError("Could not grant trust", null))
    const { findByTestId, findByText, queryByTestId } = render(Page)
    await fireEvent.click(await findByTestId("trust-code-grant"))
    await findByText("Could not grant trust")
    expect(queryByTestId("trust-code-granted")).toBeNull()
    expect(queryByTestId("trust-code-grant")).not.toBeNull()
  })

  it("shows the return message when trust was already granted", async () => {
    mockLoad.mockResolvedValue({ kind: "trusted", project_name: "Support Bot" })
    const { findByTestId, queryByTestId } = render(Page)
    expect((await findByTestId("trust-code-granted")).textContent).toContain(
      RETURN_MESSAGE,
    )
    expect(queryByTestId("trust-code-grant")).toBeNull()
  })

  it("shows a load error", async () => {
    mockLoad.mockResolvedValue({
      kind: "error",
      error: new KilnError("Project not found", null),
    })
    const { findByText, queryByTestId } = render(Page)
    await findByText("Project not found")
    await waitFor(() => expect(queryByTestId("trust-code-grant")).toBeNull())
  })
})

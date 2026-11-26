// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import CodeTrustDialog from "./code_trust_dialog.svelte"

afterEach(() => {
  cleanup()
})

describe("CodeTrustDialog", () => {
  it("asks the trust question about the code", () => {
    const { container } = render(CodeTrustDialog, {
      props: { project_id: "p1", on_trust_granted: () => {} },
    })
    const text = (container.textContent ?? "").replace(/\s+/g, " ")
    expect(text).toContain(
      "This project wants to run Python code on your machine. Only proceed if you trust the code and this project.",
    )
    expect(text).toContain("Never paste code from a stranger or the internet.")
    expect(
      container.querySelector("[data-testid='trust-warning-icon']"),
    ).not.toBeNull()
  })
})

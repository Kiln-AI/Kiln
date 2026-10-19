// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import ToolCallLogTable from "./tool_call_log_table.svelte"

const ok_entry = {
  tool_name: "llm",
  arguments: { prompt: "summarise", model: "gpt_4_1" },
  output_preview: '{"verdict": "safe"}',
  is_error: false,
  duration_ms: 128,
}

const error_entry = {
  tool_name: "llm_judge",
  arguments: { prompt: "judge" },
  output_preview: "Invalid model provider: bogus",
  is_error: true,
  duration_ms: 412,
}

describe("ToolCallLogTable", () => {
  it("renders nothing when there are no calls", () => {
    const { container } = render(ToolCallLogTable, { props: { entries: [] } })
    expect(container.querySelector('[data-testid="tool-call-log"]')).toBeNull()
  })

  it("shows the function, arguments, result, duration and status", () => {
    const { container } = render(ToolCallLogTable, {
      props: { entries: [ok_entry] },
    })
    const text = container.textContent ?? ""
    expect(text).toContain("llm")
    expect(text).toContain("gpt_4_1")
    expect(text).toContain('{"verdict": "safe"}')
    expect(text).toContain("128ms")
    expect(text).toContain("OK")
  })

  it("shows the failure reason for an errored call", () => {
    // output_preview is where the recorder puts the error message, and it is the
    // only place an author can find out why a call failed.
    const { container } = render(ToolCallLogTable, {
      props: { entries: [error_entry] },
    })
    const text = container.textContent ?? ""
    expect(text).toContain("Invalid model provider: bogus")
    expect(text).toContain("Error")
    expect(container.querySelector(".badge-error")).not.toBeNull()
  })

  it("pretty-prints a JSON result but leaves plain text alone", () => {
    const { container } = render(ToolCallLogTable, {
      props: { entries: [ok_entry, error_entry] },
    })
    const pres = Array.from(container.querySelectorAll("pre")).map(
      (el) => el.textContent ?? "",
    )
    expect(
      pres.some((t) => t.includes('"verdict": "safe"') && t.includes("\n")),
    ).toBe(true)
    expect(pres.some((t) => t === "Invalid model provider: bogus")).toBe(true)
  })

  it("uses the given title in place of the default", () => {
    const { container } = render(ToolCallLogTable, {
      props: { entries: [ok_entry], title: "Scorer Tool Calls" },
    })
    expect(container.textContent).toContain("Scorer Tool Calls")
    expect(container.textContent).not.toContain("Internal Tool Calls")
  })

  it("shows the tooltip only when one is supplied", () => {
    // InfoTooltip renders a [role="tooltip"] element; no prop, no element.
    const without = render(ToolCallLogTable, { props: { entries: [ok_entry] } })
    expect(without.container.querySelector('[role="tooltip"]')).toBeNull()

    const withTooltip = render(ToolCallLogTable, {
      props: { entries: [ok_entry], tooltip_text: "why these calls happened" },
    })
    const tooltip = withTooltip.container.querySelector('[role="tooltip"]')
    expect(tooltip).not.toBeNull()
    expect(tooltip?.textContent).toContain("why these calls happened")
  })

  it("renders a row per call", () => {
    const { container } = render(ToolCallLogTable, {
      props: { entries: [ok_entry, error_entry] },
    })
    expect(container.querySelectorAll("tbody tr").length).toBe(2)
  })
})

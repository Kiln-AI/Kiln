// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import type { TaskOutputRatingType } from "$lib/types"
import OutputTypeTablePreview from "./output_type_table_preview.svelte"

afterEach(cleanup)

// Every enum member is listed so the component's dropped {:else} fallback
// stays safe: a new rating type without a branch would render nothing.
const labels: [TaskOutputRatingType, string][] = [
  ["five_star", "1 to 5"],
  ["pass_fail", "pass/fail"],
  ["pass_fail_critical", "pass/fail/critical"],
  // Custom metrics are unbounded numbers, but the label must match the
  // "Custom Metric" wording rating_name() uses everywhere else.
  ["custom", "Custom Metric"],
]

describe("OutputTypeTablePreview", () => {
  it.each(labels)("labels %s as %s", (output_score_type, label) => {
    const { container } = render(OutputTypeTablePreview, {
      props: { output_score_type },
    })
    expect(container.textContent).toContain(label)
  })

  it("renders a tooltip explaining custom metrics", () => {
    const { container } = render(OutputTypeTablePreview, {
      props: { output_score_type: "custom" },
    })
    const tooltip = container.querySelector('[role="tooltip"]')
    expect(tooltip).not.toBeNull()
    expect(tooltip!.textContent).toContain("Any finite number")
  })
})

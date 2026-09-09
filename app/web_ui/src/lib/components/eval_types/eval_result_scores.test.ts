// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalResultScores from "./eval_result_scores.svelte"

describe("EvalResultScores", () => {
  describe("empty state", () => {
    it("shows 'No scores available.' when scores is empty and not skipped", () => {
      const { container } = render(EvalResultScores)
      expect(container.textContent).toContain("No scores available.")
    })

    it("shows 'No scores available.' with explicit empty scores", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: {}, skipped_reason: null, skipped_detail: null },
      })
      expect(container.textContent).toContain("No scores available.")
    })
  })

  describe("scores display", () => {
    it("renders a single score with toFixed(2)", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: { accuracy: 0.9 } },
      })
      expect(container.textContent).toContain("accuracy:")
      expect(container.textContent).toContain("0.90")
    })

    it("renders multiple scores", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: { accuracy: 1, relevance: 0.567 } },
      })
      expect(container.textContent).toContain("accuracy:")
      expect(container.textContent).toContain("1.00")
      expect(container.textContent).toContain("relevance:")
      expect(container.textContent).toContain("0.57")
    })

    it("formats zero as 0.00", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: { score: 0 } },
      })
      expect(container.textContent).toContain("0.00")
    })

    it("does not show skip badge when scores are present", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: { score: 0.5 } },
      })
      expect(container.textContent).not.toContain("Skipped")
    })

    it("does not show 'No scores available.' when scores are present", () => {
      const { container } = render(EvalResultScores, {
        props: { scores: { score: 0.5 } },
      })
      expect(container.textContent).not.toContain("No scores available.")
    })
  })

  describe("skipped state", () => {
    it("shows the Skipped badge when skipped_reason is set", () => {
      const { container } = render(EvalResultScores, {
        props: { skipped_reason: "missing_reference" },
      })
      expect(container.textContent).toContain("Skipped")
      expect(container.querySelector(".badge-warning")).not.toBeNull()
    })

    it("displays the skipped reason with underscores replaced by spaces", () => {
      const { container } = render(EvalResultScores, {
        props: { skipped_reason: "missing_reference_data" },
      })
      expect(container.textContent).toContain("missing reference data")
    })

    it("displays skipped_detail when provided", () => {
      const { container } = render(EvalResultScores, {
        props: {
          skipped_reason: "timeout",
          skipped_detail: "Exceeded 30s limit",
        },
      })
      expect(container.textContent).toContain("Exceeded 30s limit")
    })

    it("does not display skipped_detail when it is null", () => {
      const { container } = render(EvalResultScores, {
        props: { skipped_reason: "timeout", skipped_detail: null },
      })
      expect(container.textContent).toContain("timeout")
      expect(container.querySelector(".text-gray-400.text-xs")).toBeNull()
    })

    it("skipped takes priority over scores", () => {
      const { container } = render(EvalResultScores, {
        props: {
          scores: { accuracy: 0.9 },
          skipped_reason: "error",
          skipped_detail: null,
        },
      })
      expect(container.textContent).toContain("Skipped")
      expect(container.textContent).not.toContain("0.90")
    })

    it("does not show 'No scores available.' when skipped", () => {
      const { container } = render(EvalResultScores, {
        props: { skipped_reason: "error" },
      })
      expect(container.textContent).not.toContain("No scores available.")
    })
  })
})

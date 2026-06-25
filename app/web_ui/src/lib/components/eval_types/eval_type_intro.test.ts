// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalTypeIntro from "./eval_type_intro.svelte"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
} from "$lib/utils/eval_types/registry"

describe("EvalTypeIntro", () => {
  it("renders the type label", () => {
    const metadata = getV2EvalTypeMetadata("code_eval")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    expect(container.textContent).toContain("Code")
  })

  it("renders the explainer when available", () => {
    const metadata = getV2EvalTypeMetadata("code_eval")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    expect(container.textContent).toContain("custom Python scoring function")
  })

  it("renders explainer text for exact_match", () => {
    const metadata = getV2EvalTypeMetadata("exact_match")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    expect(container.textContent).toContain(metadata.explainer)
  })

  it("renders the eval-type-intro test id", () => {
    const metadata = getV2EvalTypeMetadata("llm_judge")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    expect(
      container.querySelector('[data-testid="eval-type-intro"]'),
    ).not.toBeNull()
  })

  it("B6: wraps content in a CalloutCard", () => {
    const metadata = getV2EvalTypeMetadata("code_eval")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    const card = container.querySelector('[data-testid="eval-type-intro-card"]')
    expect(card).not.toBeNull()
    expect(card?.classList.contains("card-bordered")).toBe(true)
    expect(card?.textContent).toContain(metadata.label)
    expect(card?.textContent).toContain(metadata.explainer)
  })

  it("renders tags for code_eval including Beta", () => {
    const metadata = getV2EvalTypeMetadata("code_eval")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    const badges = container.querySelectorAll(".badge")
    const badgeTexts = Array.from(badges).map((b) => b.textContent?.trim())
    expect(badgeTexts).toContain("Beta")
    expect(badgeTexts).toContain("Python")
  })

  it("renders tags for llm_judge", () => {
    const metadata = getV2EvalTypeMetadata("llm_judge")
    const { container } = render(EvalTypeIntro, { props: { metadata } })
    const badges = container.querySelectorAll(".badge")
    const badgeTexts = Array.from(badges).map((b) => b.textContent?.trim())
    expect(badgeTexts).toContain("Uses LLM")
    expect(badgeTexts).toContain("Graded")
  })

  it("renders tags matching the registry for every eval type", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const metadata = getV2EvalTypeMetadata(evalType)
      const { container } = render(EvalTypeIntro, { props: { metadata } })
      const badges = container.querySelectorAll(".badge")
      const badgeTexts = Array.from(badges).map((b) => b.textContent?.trim())
      for (const tag of metadata.tags) {
        expect(badgeTexts).toContain(tag.label)
      }
    }
  })
})

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
    const evalType = "code_eval" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    expect(container.textContent).toContain("Code")
  })

  it("renders the explainer when available", () => {
    const evalType = "code_eval" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    expect(container.textContent).toContain("custom Python scoring function")
  })

  it("renders explainer text for exact_match", () => {
    const evalType = "exact_match" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    expect(container.textContent).toContain(metadata.explainer)
  })

  it("renders the eval-type-intro test id", () => {
    const evalType = "llm_judge" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    expect(
      container.querySelector('[data-testid="eval-type-intro"]'),
    ).not.toBeNull()
  })

  it("B6: wraps content in a CalloutCard", () => {
    const evalType = "code_eval" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const card = container.querySelector('[data-testid="eval-type-intro-card"]')
    expect(card).not.toBeNull()
    expect(card?.classList.contains("card-bordered")).toBe(true)
    expect(card?.textContent).toContain(metadata.label)
    expect(card?.textContent).toContain(metadata.explainer)
  })

  it("renders the Beta badge for code_eval", () => {
    const evalType = "code_eval" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const badges = container.querySelectorAll(".badge")
    expect(badges).toHaveLength(1)
    expect(badges[0].textContent?.trim()).toBe("Beta")
  })

  it("renders no tag badges for llm_judge", () => {
    const evalType = "llm_judge" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const badges = container.querySelectorAll(".badge")
    expect(badges).toHaveLength(0)
  })

  it("renders no tag wrapper div for types with empty tags", () => {
    const evalType = "exact_match" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const badges = container.querySelectorAll(".badge")
    expect(badges).toHaveLength(0)
  })

  it("renders tags matching the registry for every eval type", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const metadata = getV2EvalTypeMetadata(evalType)
      const { container } = render(EvalTypeIntro, {
        props: { evalType, metadata },
      })
      const badges = container.querySelectorAll(".badge")
      const badgeTexts = Array.from(badges).map((b) => b.textContent?.trim())
      for (const tag of metadata.tags) {
        expect(badgeTexts).toContain(tag.label)
      }
    }
  })

  it('shows "Code Judge" title for code_eval (label "Code" + " Judge")', () => {
    const evalType = "code_eval" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const heading = container.querySelector(".font-medium")
    expect(heading?.textContent).toBe("Code Judge")
  })

  it('shows "Exact Match Judge" title for exact_match', () => {
    const evalType = "exact_match" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const heading = container.querySelector(".font-medium")
    expect(heading?.textContent).toBe("Exact Match Judge")
  })

  it('shows "Pattern Match Judge" title for pattern_match', () => {
    const evalType = "pattern_match" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const heading = container.querySelector(".font-medium")
    expect(heading?.textContent).toBe("Pattern Match Judge")
  })

  it('shows "Contains Judge" title for contains', () => {
    const evalType = "contains" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const heading = container.querySelector(".font-medium")
    expect(heading?.textContent).toBe("Contains Judge")
  })

  it('keeps "LLM as Judge" title (does not double "Judge")', () => {
    const evalType = "llm_judge" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const heading = container.querySelector(".font-medium")
    expect(heading?.textContent).toBe("LLM as Judge")
    expect(heading?.textContent).not.toBe("LLM as Judge Judge")
  })

  it("does not constrain the intro wrapper width", () => {
    const evalType = "exact_match" as const
    const metadata = getV2EvalTypeMetadata(evalType)
    const { container } = render(EvalTypeIntro, {
      props: { evalType, metadata },
    })
    const intro = container.querySelector("[data-testid='eval-type-intro']")
    expect(intro?.classList.contains("max-w-[600px]")).toBe(false)
  })
})

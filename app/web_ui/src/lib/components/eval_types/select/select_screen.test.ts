// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalTypeTags from "./eval_type_tags.svelte"
import EvalTypeHero from "./eval_type_hero.svelte"
import EvalTypeRow from "./eval_type_row.svelte"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
} from "$lib/utils/eval_types/registry"

describe("EvalTypeTags", () => {
  it("renders all tags", () => {
    const tags = [
      { label: "Uses LLM", tone: "default" as const },
      { label: "Graded", tone: "default" as const },
    ]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badges = container.querySelectorAll(".badge")
    expect(badges.length).toBe(2)
    expect(badges[0].textContent?.trim()).toBe("Uses LLM")
    expect(badges[1].textContent?.trim()).toBe("Graded")
  })

  it("applies default tone styling", () => {
    const tags = [{ label: "Deterministic", tone: "default" as const }]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badge = container.querySelector(".badge")!
    expect(badge.classList.contains("badge-outline")).toBe(true)
    expect(badge.classList.contains("badge-primary")).toBe(false)
  })

  it("applies beta tone styling", () => {
    const tags = [{ label: "Beta", tone: "beta" as const }]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badge = container.querySelector(".badge")!
    expect(badge.classList.contains("badge-outline")).toBe(true)
    expect(badge.classList.contains("badge-primary")).toBe(true)
  })

  it("renders mixed tone tags correctly", () => {
    const tags = [
      { label: "Python", tone: "default" as const },
      { label: "Beta", tone: "beta" as const },
    ]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badges = container.querySelectorAll(".badge")
    expect(badges[0].classList.contains("badge-primary")).toBe(false)
    expect(badges[1].classList.contains("badge-primary")).toBe(true)
  })
})

describe("EvalTypeHero", () => {
  const metadata = getV2EvalTypeMetadata("llm_judge")

  it("renders the type name", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    expect(container.textContent).toContain("LLM as Judge")
  })

  it("renders the description", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    expect(container.textContent).toContain(metadata.description)
  })

  it("renders the star Recommended badge when recommended is true", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    const badge = container.querySelector(".badge-primary")
    expect(badge).not.toBeNull()
    expect(badge?.textContent).toContain("★")
    expect(badge?.textContent).toContain("Recommended")
  })

  it("does not render the Recommended badge when recommended is falsy", () => {
    const nonRecommended = getV2EvalTypeMetadata("code_eval")
    const { container } = render(EvalTypeHero, {
      props: { metadata: nonRecommended },
    })
    expect(container.textContent).not.toContain("Recommended")
  })

  it("renders tags", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    expect(container.textContent).toContain("Uses LLM")
    expect(container.textContent).toContain("Graded")
  })

  it("renders a Continue button", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    const btn = container.querySelector(".btn-primary")
    expect(btn).not.toBeNull()
    expect(btn?.textContent?.trim()).toBe("Continue")
  })

  it("has a heavier card with bg-base-200", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    const card = container.querySelector(".card")!
    expect(card.classList.contains("bg-base-200")).toBe(true)
    expect(card.classList.contains("border-2")).toBe(true)
  })

  it("renders the type icon", () => {
    const { container } = render(EvalTypeHero, { props: { metadata } })
    const icon = container.querySelector("i")
    expect(icon).not.toBeNull()
    expect(icon?.classList.contains("bi")).toBe(true)
    expect(icon?.classList.contains("bi-robot")).toBe(true)
  })
})

describe("EvalTypeRow", () => {
  const metadata = getV2EvalTypeMetadata("code_eval")

  it("renders the type name", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    expect(container.textContent).toContain("Code")
  })

  it("renders the description", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    expect(container.textContent).toContain(metadata.description)
  })

  it("renders tags", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    expect(container.textContent).toContain("Python")
    expect(container.textContent).toContain("Beta")
  })

  it("the entire row is a button with data-testid", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    const button = container.querySelector('[data-testid="eval-type-row"]')
    expect(button).not.toBeNull()
    expect(button?.tagName).toBe("BUTTON")
  })

  it("has hover styling for interactivity", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    const card = container.querySelector(".card")!
    expect(card.classList.contains("hover:shadow-lg")).toBe(true)
    expect(card.classList.contains("hover:border-primary/50")).toBe(true)
  })

  it("renders a chevron indicator", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    const svg = container.querySelector("svg")
    expect(svg).not.toBeNull()
  })

  it("renders the type icon", () => {
    const { container } = render(EvalTypeRow, { props: { metadata } })
    const icon = container.querySelector("i")
    expect(icon).not.toBeNull()
    expect(icon?.classList.contains("bi-code-slash")).toBe(true)
  })
})

describe("select screen data-driven rendering", () => {
  it("hero type is the recommended type (first in ALL_V2_EVAL_TYPES)", () => {
    const heroType = ALL_V2_EVAL_TYPES[0]
    const heroMeta = getV2EvalTypeMetadata(heroType)
    expect(heroMeta.recommended).toBe(true)
    expect(heroType).toBe("llm_judge")
  })

  it("list types are all non-hero types", () => {
    const listTypes = ALL_V2_EVAL_TYPES.slice(1)
    expect(listTypes.length).toBe(ALL_V2_EVAL_TYPES.length - 1)
    for (const t of listTypes) {
      const meta = getV2EvalTypeMetadata(t)
      expect(meta.recommended).not.toBe(true)
    }
  })

  it("every type has tags that can be rendered", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const meta = getV2EvalTypeMetadata(t)
      expect(meta.tags.length).toBeGreaterThan(0)
      const { container } = render(EvalTypeTags, { props: { tags: meta.tags } })
      const badges = container.querySelectorAll(".badge")
      expect(badges.length).toBe(meta.tags.length)
    }
  })
})

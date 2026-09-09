// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalTypeTags from "./eval_type_tags.svelte"
import OptionList from "$lib/ui/option_list.svelte"
import { buildEvalTypeOptions } from "./eval_type_options"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
} from "$lib/utils/eval_types/registry"

describe("EvalTypeTags", () => {
  it("renders nothing for empty tags array", () => {
    const tags: { label: string; tone: "default" | "beta" }[] = []
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badges = container.querySelectorAll(".badge")
    expect(badges.length).toBe(0)
    const wrapper = container.querySelector(".flex")
    expect(wrapper).toBeNull()
  })

  it("renders a single beta tag", () => {
    const tags = [{ label: "Beta", tone: "beta" as const }]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badges = container.querySelectorAll(".badge")
    expect(badges.length).toBe(1)
    expect(badges[0].textContent?.trim()).toBe("Beta")
  })

  it("applies beta tone styling", () => {
    const tags = [{ label: "Beta", tone: "beta" as const }]
    const { container } = render(EvalTypeTags, { props: { tags } })
    const badge = container.querySelector(".badge")!
    expect(badge.classList.contains("badge-outline")).toBe(true)
    expect(badge.classList.contains("badge-primary")).toBe(true)
  })
})

describe("buildEvalTypeOptions", () => {
  it("returns one option per eval type, in registry order", () => {
    const options = buildEvalTypeOptions()
    expect(options.map((o) => o.id)).toEqual([...ALL_V2_EVAL_TYPES])
  })

  it("maps each option's name and description from metadata", () => {
    const options = buildEvalTypeOptions()
    for (const option of options) {
      const metadata = getV2EvalTypeMetadata(
        option.id as (typeof ALL_V2_EVAL_TYPES)[number],
      )
      expect(option.name).toBe(metadata.label)
      expect(option.description).toBe(metadata.description)
    }
  })

  it("marks only the recommended registry type as recommended", () => {
    const options = buildEvalTypeOptions()
    for (const option of options) {
      const metadata = getV2EvalTypeMetadata(
        option.id as (typeof ALL_V2_EVAL_TYPES)[number],
      )
      expect(option.recommended).toBe(metadata.recommended ?? false)
    }
    expect(options.filter((o) => o.recommended)).toHaveLength(1)
    expect(options.find((o) => o.recommended)?.id).toBe("llm_judge")
  })

  it("provides an icon component for every option", () => {
    const options = buildEvalTypeOptions()
    for (const option of options) {
      expect(option.icon, `${option.id} should have an icon`).toBeTruthy()
    }
  })
})

describe("judge type picker (OptionList)", () => {
  it("renders one clickable button row per eval type", () => {
    const { container } = render(OptionList, {
      props: { options: buildEvalTypeOptions(), select_option: () => {} },
    })
    const buttons = container.querySelectorAll("button")
    expect(buttons.length).toBe(ALL_V2_EVAL_TYPES.length)
  })

  it("renders a single star Recommended badge for the recommended type", () => {
    const { container } = render(OptionList, {
      props: { options: buildEvalTypeOptions(), select_option: () => {} },
    })
    const recommendedBadges = Array.from(
      container.querySelectorAll(".badge-primary"),
    ).filter((b) => b.textContent?.includes("Recommended"))
    expect(recommendedBadges).toHaveLength(1)
  })

  it("renders a chevron indicator on each row", () => {
    const { container } = render(OptionList, {
      props: { options: buildEvalTypeOptions(), select_option: () => {} },
    })
    const svgs = container.querySelectorAll("svg")
    // At least one chevron per row.
    expect(svgs.length).toBeGreaterThanOrEqual(ALL_V2_EVAL_TYPES.length)
  })
})

describe("select screen data-driven rendering", () => {
  it("recommended type is the first in ALL_V2_EVAL_TYPES", () => {
    const recommendedType = ALL_V2_EVAL_TYPES[0]
    const meta = getV2EvalTypeMetadata(recommendedType)
    expect(meta.recommended).toBe(true)
    expect(recommendedType).toBe("llm_judge")
  })

  it("all types after the first are non-recommended", () => {
    const rest = ALL_V2_EVAL_TYPES.slice(1)
    expect(rest.length).toBe(ALL_V2_EVAL_TYPES.length - 1)
    for (const t of rest) {
      const meta = getV2EvalTypeMetadata(t)
      expect(meta.recommended).not.toBe(true)
    }
  })

  it("only code_eval renders tag badges (Beta); all others render none", () => {
    for (const t of ALL_V2_EVAL_TYPES) {
      const meta = getV2EvalTypeMetadata(t)
      const { container } = render(EvalTypeTags, { props: { tags: meta.tags } })
      const badges = container.querySelectorAll(".badge")
      if (t === "code_eval") {
        expect(badges.length).toBe(1)
        expect(badges[0].textContent?.trim()).toBe("Beta")
      } else {
        expect(badges.length).toBe(0)
      }
    }
  })
})

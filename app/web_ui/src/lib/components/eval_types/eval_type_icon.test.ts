// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import EvalTypeIcon, { getEvalTypeIconComponent } from "./eval_type_icon.svelte"
import OptionList from "$lib/ui/option_list.svelte"
import EvalTypeIntro from "./eval_type_intro.svelte"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
  type V2EvalType,
} from "$lib/utils/eval_types/registry"

function renderEvalTypeOptionList(evalType: V2EvalType) {
  const metadata = getV2EvalTypeMetadata(evalType)
  return render(OptionList, {
    props: {
      options: [
        {
          id: evalType,
          name: metadata.label,
          description: metadata.description,
          icon: getEvalTypeIconComponent(evalType),
        },
      ],
      select_option: () => {},
    },
  })
}

describe("EvalTypeIcon", () => {
  it("renders a non-empty SVG for every V2 eval type", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const { container } = render(EvalTypeIcon, { props: { evalType } })
      const svg = container.querySelector("svg")
      expect(svg, `${evalType} should render an SVG`).not.toBeNull()
      expect(
        svg!.innerHTML.trim().length,
        `${evalType} SVG should not be empty`,
      ).toBeGreaterThan(0)
    }
  })

  it("every icon SVG has aria-hidden for accessibility", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const { container } = render(EvalTypeIcon, { props: { evalType } })
      const svg = container.querySelector("svg")
      expect(svg).not.toBeNull()
      expect(
        svg!.getAttribute("aria-hidden"),
        `${evalType} icon should be aria-hidden`,
      ).toBe("true")
    }
  })

  it("every icon inherits currentColor via stroke", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const { container } = render(EvalTypeIcon, { props: { evalType } })
      const svg = container.querySelector("svg")
      expect(svg).not.toBeNull()
      const svgHtml = svg!.outerHTML
      expect(svgHtml, `${evalType} icon should use currentColor`).toContain(
        "currentColor",
      )
    }
  })

  it("renders distinct SVG content for each eval type", () => {
    const svgContents = new Map<V2EvalType, string>()
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const { container } = render(EvalTypeIcon, { props: { evalType } })
      const svg = container.querySelector("svg")
      expect(svg).not.toBeNull()
      svgContents.set(evalType, svg!.innerHTML)
    }
    const uniqueContents = new Set(svgContents.values())
    expect(uniqueContents.size).toBe(ALL_V2_EVAL_TYPES.length)
  })
})

describe("EvalTypeIcon renders in the option list", () => {
  it("every eval type option renders an SVG icon (no empty squares)", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const { container } = renderEvalTypeOptionList(evalType)
      const iconSvg = container.querySelector(".option-icon svg")
      expect(
        iconSvg,
        `${evalType} option should have an icon SVG`,
      ).not.toBeNull()
      expect(
        iconSvg!.innerHTML.trim().length,
        `${evalType} option icon SVG should not be empty`,
      ).toBeGreaterThan(0)
    }
  })
})

describe("EvalTypeIcon renders in eval_type_intro", () => {
  it("every eval type intro renders an SVG icon (no empty squares)", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const metadata = getV2EvalTypeMetadata(evalType)
      const { container } = render(EvalTypeIntro, {
        props: { evalType, metadata },
      })
      const svgs = container.querySelectorAll("svg")
      expect(
        svgs.length,
        `${evalType} intro should have SVG icons`,
      ).toBeGreaterThanOrEqual(1)
      const iconContainer = container.querySelector('[aria-hidden="true"]')
      expect(
        iconContainer,
        `${evalType} intro should have an aria-hidden icon container`,
      ).not.toBeNull()
      const iconSvg = iconContainer!.querySelector("svg")
      expect(
        iconSvg,
        `${evalType} intro should have an icon SVG`,
      ).not.toBeNull()
    }
  })
})

describe("Same icon in option list and intro", () => {
  it("renders the same icon SVG for a given type in both option list and intro", () => {
    for (const evalType of ALL_V2_EVAL_TYPES) {
      const metadata = getV2EvalTypeMetadata(evalType)

      const { container: optionContainer } = renderEvalTypeOptionList(evalType)
      const optionIcon = optionContainer.querySelector(".option-icon svg")
      expect(optionIcon, `${evalType} option icon`).not.toBeNull()

      const { container: introContainer } = render(EvalTypeIntro, {
        props: { evalType, metadata },
      })
      const introIcon = introContainer.querySelector('[aria-hidden="true"] svg')
      expect(introIcon, `${evalType} intro icon`).not.toBeNull()

      expect(
        optionIcon!.innerHTML,
        `${evalType} should have the same icon in option list and intro`,
      ).toBe(introIcon!.innerHTML)
    }
  })
})

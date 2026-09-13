// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import SettingsHeader from "./settings_header.svelte"
import SettingsHeaderActionsHarness from "./settings_header_actions_harness.test.svelte"

afterEach(() => cleanup())

// What every caller without actions renders. Pinned so the actions slot added
// alongside it cannot change the header they already have.
describe("settings_header — no actions", () => {
  it("renders the title, and the subtitle only when given one", () => {
    const plain = render(SettingsHeader, { props: { title: "Overview" } })
    const rule = plain.container.querySelector("div")!
    expect(rule.className).toContain("border-b")
    expect(rule.querySelector("h2")!.textContent).toBe("Overview")
    expect(rule.querySelector("p")).toBeNull()
    // The title is the header's only child: no wrapper comes between them.
    expect(rule.firstElementChild!.tagName).toBe("H2")
    cleanup()

    const titled = render(SettingsHeader, {
      props: { title: "Overview", subtitle: "What happened here" },
    })
    expect(titled.container.querySelector("p")!.textContent).toBe(
      "What happened here",
    )
  })
})

describe("settings_header — with actions", () => {
  it("puts the actions on the title's line, inside the header's own rule", () => {
    const { container } = render(SettingsHeaderActionsHarness, {
      props: { title: "Overview" },
    })
    const rule = container.querySelector(".border-b")!
    const action = container.querySelector("[data-action]")!
    // Inside the rule, so the rule still spans the full width.
    expect(action.closest(".border-b")).toBe(rule)
    // Beside the title, not under it: the title's box and the actions' box
    // are children of one row, and that row is the thing laying them out.
    const title_box = rule.querySelector("h2")!.parentElement!
    const action_box = action.parentElement!
    expect(action_box).not.toBe(title_box)
    expect(title_box.parentElement).toBe(action_box.parentElement)
    const row = title_box.parentElement!
    expect(row.className).toContain("flex")
    expect(row.className).toContain("justify-between")
  })
})

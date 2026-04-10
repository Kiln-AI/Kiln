// @vitest-environment jsdom
import { describe, it, expect } from "vitest"
import { render } from "@testing-library/svelte"
import TableActionMenu from "./table_action_menu.svelte"
import type { FloatingMenuItem } from "./floating_menu_types"

describe("TableActionMenu component", () => {
  it("renders the ellipsis button when items are visible", () => {
    const items: FloatingMenuItem[] = [
      { label: "Edit", onclick: () => {} },
      { label: "Delete", onclick: () => {} },
    ]
    const { container } = render(TableActionMenu, { props: { items } })
    const button = container.querySelector('[aria-label="More options"]')
    expect(button).not.toBeNull()
    const svg = container.querySelector("svg")
    expect(svg).not.toBeNull()
  })

  it("renders nothing when all items are hidden", () => {
    const items: FloatingMenuItem[] = [
      { label: "Edit", onclick: () => {}, hidden: true },
    ]
    const { container } = render(TableActionMenu, { props: { items } })
    expect(container.querySelector('[aria-label="More options"]')).toBeNull()
  })

  it("passes items through to FloatingMenu", () => {
    const items: FloatingMenuItem[] = [
      { label: "Clone", onclick: () => {} },
      { label: "View", href: "/view" },
    ]
    const { container } = render(TableActionMenu, { props: { items } })
    expect(
      container.querySelector('[aria-label="More options"]'),
    ).not.toBeNull()
  })
})

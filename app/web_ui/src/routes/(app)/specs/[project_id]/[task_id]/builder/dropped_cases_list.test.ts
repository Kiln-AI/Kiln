// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { cleanup, render } from "@testing-library/svelte"
import DroppedCasesList from "./dropped_cases_list.svelte"

afterEach(() => cleanup())

function drops(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    scenario_index: i,
    scenario: `Scenario ${i}`,
    drop_detail: `Reason ${i}`,
  }))
}

function rows(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>("[data-dropped-case]")]
}

function in_collapse(row: HTMLElement): boolean {
  return row.closest(".collapse") !== null
}

describe("DroppedCasesList", () => {
  it("lists each dropped scenario with its reason", () => {
    const { container, getByText } = render(DroppedCasesList, {
      props: { drops: drops(2) },
    })
    expect(getByText("Dropped Conversations")).toBeTruthy()
    const listed = rows(container)
    expect(listed).toHaveLength(2)
    expect(listed[0].textContent).toContain("Scenario 0")
    expect(listed[0].textContent).toContain("Reason 0")
    expect(listed[1].textContent).toContain("Reason 1")
    expect(container.querySelector(".collapse")).toBeNull()
  })

  it("shows the first five and puts the rest behind a collapse", () => {
    const { container, getByText } = render(DroppedCasesList, {
      props: { drops: drops(8) },
    })
    const listed = rows(container)
    expect(listed).toHaveLength(8)
    expect(listed.filter((r) => !in_collapse(r))).toHaveLength(5)
    expect(listed.filter(in_collapse)).toHaveLength(3)
    expect(getByText("3 More")).toBeTruthy()
  })

  it("keeps exactly five rows in view with no collapse", () => {
    const { container } = render(DroppedCasesList, {
      props: { drops: drops(5) },
    })
    expect(rows(container)).toHaveLength(5)
    expect(container.querySelector(".collapse")).toBeNull()
  })
})

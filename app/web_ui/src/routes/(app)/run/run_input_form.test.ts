// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"

// The form registers its nested fields from onMount.
vi.mock("svelte", async (importOriginal) =>
  (await import("$lib/test_support/browser_svelte")).browser_svelte(
    importOriginal,
  ),
)

const RunInputForm = (await import("./run_input_form.svelte")).default

const SCHEMA = JSON.stringify({
  type: "object",
  properties: {
    company: { type: "string", enum: ["acme", "beta"] },
    note: { type: "string" },
    seed: { type: "integer" },
    verbose: { type: "boolean" },
    tags: { type: "array", items: { type: "string" } },
    user: {
      type: "object",
      properties: { id: { type: "integer" }, name: { type: "string" } },
    },
  },
  required: [],
})

afterEach(() => cleanup())

function render_form(input_schema: string | null = SCHEMA) {
  return render(RunInputForm, { props: { input_schema } })
}

describe("run_input_form structured value", () => {
  it("starts empty without set_structured_input_data", () => {
    const { component } = render_form()
    expect(component.get_structured_input_data()).toEqual({})
  })

  it("fills every kind of field from set_structured_input_data", async () => {
    const { component } = render_form()
    const value = {
      company: "beta",
      note: "hello",
      seed: 7,
      verbose: false,
      tags: ["a", "b"],
      user: { id: 3, name: "Sam" },
    }
    await component.set_structured_input_data(value)
    expect(component.get_structured_input_data()).toEqual(value)
  })

  it("leaves fields with no value empty", async () => {
    const { component } = render_form()
    await component.set_structured_input_data({ user: { name: "Sam" } })
    expect(component.get_structured_input_data()).toEqual({
      user: { name: "Sam" },
    })
  })

  it("shows Not Set on an optional enum and asks for a pick on a required one", () => {
    const { container } = render_form(
      JSON.stringify({
        type: "object",
        properties: {
          company: { type: "string", enum: ["acme", "beta"] },
          plan: { type: "string", enum: ["free", "pro"] },
        },
        required: ["plan"],
      }),
    )
    const closed_labels = Array.from(
      container.querySelectorAll("span.truncate"),
    ).map((el) => el.textContent?.trim())
    expect(closed_labels).toEqual(["Not Set", "Select an option"])
  })

  it.each([
    ["an integer enum set to 0", { level: 0, flag: true }],
    ["a boolean enum set to false", { level: 2, flag: false }],
  ])("keeps a required %s", async (_, value) => {
    const { component } = render_form(
      JSON.stringify({
        type: "object",
        properties: {
          level: { type: "integer", enum: [0, 1, 2] },
          flag: { type: "boolean", enum: [true, false] },
        },
        required: ["level", "flag"],
      }),
    )
    await component.set_structured_input_data(value)
    expect(component.get_structured_input_data()).toEqual(value)
  })

  it("shows a prefilled boolean enum as selected", async () => {
    const { component, container } = render_form(
      JSON.stringify({
        type: "object",
        properties: {
          flag: { type: "boolean", enum: [true, false] },
          always: { type: "boolean", enum: [true] },
        },
        required: ["flag", "always"],
      }),
    )
    await component.set_structured_input_data({ flag: false, always: true })
    await tick()
    const closed_labels = Array.from(
      container.querySelectorAll("span.truncate"),
    ).map((el) => el.textContent?.trim())
    expect(closed_labels).toEqual(["false", "true"])
    expect(component.get_structured_input_data()).toEqual({
      flag: false,
      always: true,
    })
  })

  it("is a no-op in plaintext mode", async () => {
    const { component } = render_form(null)
    await component.set_structured_input_data({ note: "hello" })
    expect(component.get_plaintext_input_data()).toBe("")
    expect(component.get_structured_input_data()).toBeNull()
  })
})

// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest"
import { render, cleanup } from "@testing-library/svelte"
import { tick } from "svelte"
import SchemaSection from "./schema_section.svelte"

afterEach(() => cleanup())

// A schema authored via the API / raw JSON editor that the visual editor cannot
// represent: the root has no `additionalProperties: false`, properties use union
// types ("string" | "null"), and an open object (`additionalProperties: true`).
// This is the shape that previously crashed Clone Task with
// "Invalid schema string: not a valid JSON schema object with properties".
const unsupported_schema = JSON.stringify(
  {
    type: "object",
    properties: {
      priorMessages: {
        type: "array",
        items: {
          type: "object",
          properties: {
            id: { type: "string" },
            replyToId: { type: ["string", "null"] },
          },
          required: ["id"],
        },
      },
      channelContext: { type: ["string", "null"] },
      _eval_metadata: { type: "object", additionalProperties: true },
    },
    required: ["priorMessages"],
  },
  null,
  2,
)

const supported_schema = JSON.stringify({
  type: "object",
  additionalProperties: false,
  properties: {
    name: { title: "Name", type: "string" },
  },
  required: ["name"],
})

describe("SchemaSection raw-editor fallback", () => {
  it("falls back to the raw editor for schemas the visual editor can't represent", async () => {
    const { container, getByLabelText } = render(SchemaSection, {
      props: { schema_string: unsupported_schema },
    })
    await tick()

    // The raw JSON textarea is shown, with the schema preserved verbatim.
    const textarea = getByLabelText("Raw JSON Schema") as HTMLTextAreaElement
    expect(textarea).not.toBeNull()
    expect(textarea.value).toBe(unsupported_schema)

    // "Structured JSON" radio is selected (not plain text).
    const radios = container.querySelectorAll<HTMLInputElement>(
      'input[type="radio"]',
    )
    const structured = Array.from(radios).find((r) => r.value === "false")
    expect(structured?.checked).toBe(true)
  })

  it("returns the unsupported schema verbatim from get_schema_string", async () => {
    const { component } = render(SchemaSection, {
      props: { schema_string: unsupported_schema },
    })
    await tick()
    expect(component.get_schema_string("output_schema")).toBe(
      unsupported_schema,
    )
  })

  it("opens supported schemas in the visual editor, not the raw editor", async () => {
    const { queryByLabelText } = render(SchemaSection, {
      props: { schema_string: supported_schema },
    })
    await tick()
    expect(queryByLabelText("Raw JSON Schema")).toBeNull()
  })

  it("treats a missing schema as plain text", async () => {
    const { component, queryByLabelText } = render(SchemaSection, {
      props: { schema_string: null },
    })
    await tick()
    expect(queryByLabelText("Raw JSON Schema")).toBeNull()
    expect(component.get_schema_string("output_schema")).toBe(null)
  })
})

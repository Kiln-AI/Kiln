import { describe, it, expect, vi } from "vitest"
import { load_language_extension } from "./code_editor_language"

vi.mock("@codemirror/lang-json", () => ({ json: () => "json-language" }))
vi.mock("@codemirror/lang-python", () => ({ python: () => "python-language" }))

describe("load_language_extension", () => {
  it("loads Python", async () => {
    await expect(load_language_extension("python")).resolves.toBe(
      "python-language",
    )
  })

  it("loads JSON", async () => {
    await expect(load_language_extension("json")).resolves.toBe("json-language")
  })
})

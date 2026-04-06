import { describe, it, expect } from "vitest"
import {
  doc_skill_templates,
  DEFAULT_CONTENT_HEADER,
  type DocSkillTemplate,
} from "./doc_skill_templates"

describe("doc_skill_templates", () => {
  it("should export three templates", () => {
    const keys = Object.keys(doc_skill_templates)
    expect(keys).toHaveLength(3)
    expect(keys).toContain("small_context")
    expect(keys).toContain("medium_context")
    expect(keys).toContain("large_context")
  })

  describe("each template", () => {
    const templates = Object.entries(doc_skill_templates)

    it.each(templates)(
      "%s has all required fields",
      (_key: string, template: DocSkillTemplate) => {
        expect(template.name).toBeTruthy()
        expect(template.preview_description).toBeTruthy()
        expect(template.preview_subtitle).toBeTruthy()
        expect(template.required_provider).toBeTruthy()
        expect(template.doc_skill_name).toBeTruthy()
      },
    )

    it.each(templates)(
      "%s has valid extractor config",
      (_key: string, template: DocSkillTemplate) => {
        expect(template.extractor.config_name).toBeTruthy()
        expect(template.extractor.description).toBeTruthy()
        expect(template.extractor.model_provider_name).toBeTruthy()
        expect(template.extractor.model_name).toBeTruthy()
      },
    )

    it.each(templates)(
      "%s has valid chunker config with zero overlap",
      (_key: string, template: DocSkillTemplate) => {
        expect(template.chunker.config_name).toBeTruthy()
        expect(template.chunker.description).toBeTruthy()
        expect(template.chunker.chunk_size).toBeGreaterThan(0)
        expect(template.chunker.chunk_overlap).toBe(0)
      },
    )

    it.each(templates)(
      "%s uses GeminiOrOpenRouter",
      (_key: string, template: DocSkillTemplate) => {
        expect(template.required_provider).toBe("GeminiOrOpenRouter")
      },
    )
  })

  it("should have increasing chunk sizes", () => {
    expect(doc_skill_templates.small_context.chunker.chunk_size).toBe(1000)
    expect(doc_skill_templates.medium_context.chunker.chunk_size).toBe(2000)
    expect(doc_skill_templates.large_context.chunker.chunk_size).toBe(3000)
  })

  it("DEFAULT_CONTENT_HEADER is non-empty", () => {
    expect(DEFAULT_CONTENT_HEADER).toBeTruthy()
    expect(DEFAULT_CONTENT_HEADER.length).toBeGreaterThan(10)
  })
})

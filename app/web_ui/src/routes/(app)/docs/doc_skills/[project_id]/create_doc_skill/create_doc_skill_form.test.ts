import { describe, it, expect } from "vitest"
import { skill_name_validator } from "$lib/utils/input_validators"
import { DEFAULT_CONTENT_HEADER } from "../add_doc_skill/doc_skill_templates"

describe("create_doc_skill_form validation", () => {
  describe("skill_name_validator", () => {
    it("rejects empty values", () => {
      expect(skill_name_validator("")).not.toBeNull()
      expect(skill_name_validator(null)).not.toBeNull()
      expect(skill_name_validator(undefined)).not.toBeNull()
    })

    it("accepts valid kebab-case names", () => {
      expect(skill_name_validator("company-docs")).toBeNull()
      expect(skill_name_validator("api-reference")).toBeNull()
      expect(skill_name_validator("my-skill-123")).toBeNull()
      expect(skill_name_validator("docs")).toBeNull()
    })

    it("rejects names with uppercase letters", () => {
      expect(skill_name_validator("Company-Docs")).not.toBeNull()
      expect(skill_name_validator("DOCS")).not.toBeNull()
    })

    it("rejects names with spaces", () => {
      expect(skill_name_validator("company docs")).not.toBeNull()
    })

    it("rejects names with underscores", () => {
      expect(skill_name_validator("company_docs")).not.toBeNull()
    })

    it("rejects names starting with a hyphen", () => {
      expect(skill_name_validator("-company-docs")).not.toBeNull()
    })

    it("rejects names ending with a hyphen", () => {
      expect(skill_name_validator("company-docs-")).not.toBeNull()
    })

    it("rejects names with consecutive hyphens", () => {
      expect(skill_name_validator("company--docs")).not.toBeNull()
    })

    it("rejects names starting with a number", () => {
      expect(skill_name_validator("123-docs")).not.toBeNull()
    })

    it("rejects names longer than 64 characters", () => {
      const long_name = "a" + "-abcd".repeat(16)
      expect(long_name.length).toBeGreaterThan(64)
      expect(skill_name_validator(long_name)).not.toBeNull()
    })

    it("accepts names up to 64 characters", () => {
      const name_64 = "a".repeat(64)
      expect(skill_name_validator(name_64)).toBeNull()
    })
  })

  describe("required fields", () => {
    it("skill_name is required (empty string fails validation)", () => {
      expect(skill_name_validator("")).not.toBeNull()
    })

    it("skill_content_header has a non-empty default", () => {
      expect(DEFAULT_CONTENT_HEADER).toBeTruthy()
      expect(DEFAULT_CONTENT_HEADER.trim().length).toBeGreaterThan(0)
    })
  })
})

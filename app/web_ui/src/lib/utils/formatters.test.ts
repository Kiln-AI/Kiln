import { describe, it, expect } from "vitest"
import { formatSize, mime_type_to_string, capitalize } from "./formatters"

describe("formatters", () => {
  describe("formatSize", () => {
    const testCases = [
      { a: 0, expected: "0 B" },
      { a: 1024, expected: "1 KB" },
      { a: 1024 * 1024, expected: "1 MB" },
      { a: 1024 * 1024 * 1024, expected: "1 GB" },
      { a: 1024 * 1024 * 1024 * 1024, expected: "1 TB" },
      { a: 3, expected: "3 B" },
      { a: 3.5 * 1024, expected: "3.5 KB" },
      { a: 3.5 * 1024 * 1024, expected: "3.5 MB" },
      { a: 3.5 * 1024 * 1024 * 1024, expected: "3.5 GB" },
      { a: 3.5 * 1024 * 1024 * 1024 * 1024, expected: "3.5 TB" },
      { a: 15, expected: "15 B" },
      { a: 15.5 * 1024, expected: "15.5 KB" },
      { a: 15.5 * 1024 * 1024, expected: "15.5 MB" },
      { a: 15.5 * 1024 * 1024 * 1024, expected: "15.5 GB" },
      { a: 15.5 * 1024 * 1024 * 1024 * 1024, expected: "15.5 TB" },
      { a: 15 * 1024 * 1024 * 1024 * 1024, expected: "15 TB" },
    ]

    testCases.forEach(({ a, expected }) => {
      it(`should return ${expected} when formatting ${a}`, () => {
        expect(formatSize(a)).toBe(expected)
      })
    })

    it("should return unknown when the size is undefined", () => {
      expect(formatSize(undefined)).toBe("unknown")
    })

    it("should return unknown when the size is null", () => {
      expect(formatSize(null)).toBe("unknown")
    })

    it("should return unknown when the size is negative", () => {
      expect(formatSize(-1)).toBe("unknown")
    })

    it("should return unknown when the size is NaN", () => {
      expect(formatSize(NaN)).toBe("unknown")
    })
  })

  describe("mime_type_to_string", () => {
    it("should handle specific PDF mime type", () => {
      expect(mime_type_to_string("application/pdf")).toBe("PDF")
    })

    it("should handle specific CSV mime type", () => {
      expect(mime_type_to_string("text/csv")).toBe("CSV")
    })

    it("should handle specific Markdown mime type", () => {
      expect(mime_type_to_string("text/markdown")).toBe("Markdown")
    })

    it("should handle specific HTML mime type", () => {
      expect(mime_type_to_string("text/html")).toBe("HTML")
    })

    it("should handle specific plain text mime type", () => {
      expect(mime_type_to_string("text/plain")).toBe("Text")
    })

    describe("generic image types", () => {
      const imageTestCases = [
        { input: "image/jpeg", expected: "Image (jpeg)" },
        { input: "image/png", expected: "Image (png)" },
        { input: "image/gif", expected: "Image (gif)" },
        { input: "image/webp", expected: "Image (webp)" },
        { input: "image/svg+xml", expected: "Image (svg+xml)" },
      ]

      imageTestCases.forEach(({ input, expected }) => {
        it(`should return ${expected} for ${input}`, () => {
          expect(mime_type_to_string(input)).toBe(expected)
        })
      })
    })

    describe("generic text types", () => {
      const textTestCases = [
        { input: "text/xml", expected: "Text (xml)" },
        { input: "text/json", expected: "Text (json)" },
        { input: "text/javascript", expected: "Text (javascript)" },
        { input: "text/css", expected: "Text (css)" },
      ]

      textTestCases.forEach(({ input, expected }) => {
        it(`should return ${expected} for ${input}`, () => {
          expect(mime_type_to_string(input)).toBe(expected)
        })
      })
    })

    describe("generic video types", () => {
      const videoTestCases = [
        { input: "video/mp4", expected: "Video (mp4)" },
        { input: "video/webm", expected: "Video (webm)" },
        { input: "video/avi", expected: "Video (avi)" },
        { input: "video/quicktime", expected: "Video (quicktime)" },
      ]

      videoTestCases.forEach(({ input, expected }) => {
        it(`should return ${expected} for ${input}`, () => {
          expect(mime_type_to_string(input)).toBe(expected)
        })
      })
    })

    describe("generic audio types", () => {
      const audioTestCases = [
        { input: "audio/mp3", expected: "Audio (mp3)" },
        { input: "audio/wav", expected: "Audio (wav)" },
        { input: "audio/ogg", expected: "Audio (ogg)" },
        { input: "audio/mpeg", expected: "Audio (mpeg)" },
      ]

      audioTestCases.forEach(({ input, expected }) => {
        it(`should return ${expected} for ${input}`, () => {
          expect(mime_type_to_string(input)).toBe(expected)
        })
      })
    })

    describe("fallback cases", () => {
      const fallbackTestCases = [
        "application/json",
        "application/xml",
        "application/zip",
        "unknown/type",
        "custom-mime-type",
      ]

      fallbackTestCases.forEach((input) => {
        it(`should return original mime type for unhandled type: ${input}`, () => {
          expect(mime_type_to_string(input)).toBe(input)
        })
      })
    })
  })

  describe("capitalize", () => {
    it("should return empty string for empty string", () => {
      expect(capitalize("")).toBe("")
    })

    it("should return empty string for null", () => {
      expect(capitalize(null)).toBe("")
    })

    it("should return empty string for undefined", () => {
      expect(capitalize(undefined)).toBe("")
    })

    it("should capitalize single character", () => {
      expect(capitalize("a")).toBe("A")
    })

    it("should capitalize first letter of lowercase word", () => {
      expect(capitalize("hello")).toBe("Hello")
    })

    it("should keep first letter uppercase if already capitalized", () => {
      expect(capitalize("Hello")).toBe("Hello")
    })

    it("should only capitalize first letter, keeping rest as-is", () => {
      expect(capitalize("hELLO")).toBe("HELLO")
    })

    it("should handle mixed case strings", () => {
      expect(capitalize("hElLo WoRlD")).toBe("HElLo WoRlD")
    })

    it("should handle strings with numbers", () => {
      expect(capitalize("123abc")).toBe("123abc")
    })

    it("should handle strings starting with special characters", () => {
      expect(capitalize("!hello")).toBe("!hello")
    })

    it("should handle strings with spaces", () => {
      expect(capitalize(" hello")).toBe(" hello")
    })
  })
})

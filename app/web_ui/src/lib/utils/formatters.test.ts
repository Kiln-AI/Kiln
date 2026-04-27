import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  formatDate,
  formatSize,
  mime_type_to_string,
  capitalize,
} from "./formatters"

import type { StructuredOutputMode } from "$lib/types"
import { structuredOutputModeToString } from "./formatters"

describe("formatDate", () => {
  // Pin "now" to 2026-04-16T13:26:04.806Z for all tests.
  // This is a fixed UTC instant; the local representation depends on the
  // runner's TZ, but relative-time math is TZ-independent since both
  // Date.now() and Date.parse() return epoch-ms.
  const FAKE_NOW = new Date("2026-04-16T13:26:04.806Z")

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(FAKE_NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // -- edge cases --

  it('returns "Unknown" for undefined', () => {
    expect(formatDate(undefined)).toBe("Unknown")
  })

  it('returns "Unknown" for empty string', () => {
    expect(formatDate("")).toBe("Unknown")
  })

  // -- "just now" (< 60 s ago) --

  it('returns "just now" for UTC Z timestamp within last minute', () => {
    expect(formatDate("2026-04-16T13:25:30.000Z")).toBe("just now")
  })

  it('returns "just now" for negative-offset timestamp within last minute', () => {
    // Same instant as 13:25:30Z expressed in UTC-4
    expect(formatDate("2026-04-16T09:25:30.000-04:00")).toBe("just now")
  })

  it('returns "just now" for positive-offset timestamp within last minute', () => {
    // Same instant as 13:25:30Z expressed in UTC+8
    expect(formatDate("2026-04-16T21:25:30.000+08:00")).toBe("just now")
  })

  // -- "1 minute ago" (60-119 s) --

  it('returns "1 minute ago" for UTC Z timestamp ~90 s ago', () => {
    // 90 seconds before FAKE_NOW
    expect(formatDate("2026-04-16T13:24:34.806Z")).toBe("1 minute ago")
  })

  it('returns "1 minute ago" for offset timestamp ~90 s ago', () => {
    expect(formatDate("2026-04-16T09:24:34.806-04:00")).toBe("1 minute ago")
  })

  // -- "N minutes ago" (2-59 min) --

  it('returns "N minutes ago" for UTC Z timestamp 10 min ago', () => {
    expect(formatDate("2026-04-16T13:16:04.806Z")).toBe("10 minutes ago")
  })

  it('returns "N minutes ago" for positive-offset timestamp 25 min ago', () => {
    // 25 min before FAKE_NOW = 13:01:04.806Z = 21:01:04.806+08:00
    expect(formatDate("2026-04-16T21:01:04.806+08:00")).toBe("25 minutes ago")
  })

  it('returns "N minutes ago" for negative-offset timestamp 25 min ago', () => {
    // 25 min before FAKE_NOW = 13:01:04.806Z = 09:01:04.806-04:00
    expect(formatDate("2026-04-16T09:01:04.806-04:00")).toBe("25 minutes ago")
  })

  // -- "today" (same calendar day in local TZ, > 1 hour ago) --

  it('returns time + "today" for a timestamp earlier today', () => {
    // 2 hours before FAKE_NOW in UTC. Whether this counts as "today" depends
    // on the runner's local TZ (the function compares date.toDateString() to
    // new Date().toDateString()). We compute the expected value the same way
    // the function does so the test is TZ-independent.
    const twoHoursAgo = new Date(FAKE_NOW.getTime() - 2 * 60 * 60 * 1000)
    const sameDayLocally =
      twoHoursAgo.toDateString() === FAKE_NOW.toDateString()

    const result = formatDate(twoHoursAgo.toISOString())

    if (sameDayLocally) {
      expect(result).toContain("today")
    } else {
      // Near midnight in local TZ the 2-hour-ago timestamp might fall on the
      // previous calendar day. In that case we get a full date string, which
      // is also correct behavior.
      expect(result).not.toBe("Unknown")
      expect(result).not.toContain("minutes ago")
    }
  })

  // -- older date (different calendar day) --

  it("returns full formatted date for a timestamp from yesterday (Z)", () => {
    const result = formatDate("2026-04-15T10:00:00.000Z")
    expect(result).not.toBe("Unknown")
    expect(result).not.toContain("ago")
    // Should contain year, date digits, and am/pm
    expect(result).toMatch(/2026/)
  })

  it("returns full formatted date for an offset timestamp from yesterday", () => {
    const result = formatDate("2026-04-15T06:00:00.000-04:00")
    expect(result).not.toBe("Unknown")
    expect(result).not.toContain("ago")
    expect(result).toMatch(/2026/)
  })

  // -- legacy naive ISO (no offset, no Z) --
  // JS Date parses naive ISO as local time, which matches the legacy
  // assumption that the writer and reader share the same TZ.

  it('returns "just now" for a legacy naive ISO string within last minute', () => {
    // Build a naive ISO string that represents "30 seconds ago" in the
    // runner's local TZ. We derive it from FAKE_NOW so the test is
    // deterministic regardless of which TZ the runner uses.
    const thirtySecsAgo = new Date(FAKE_NOW.getTime() - 30_000)
    const pad = (n: number) => String(n).padStart(2, "0")
    const naive =
      `${thirtySecsAgo.getFullYear()}-${pad(thirtySecsAgo.getMonth() + 1)}-${pad(thirtySecsAgo.getDate())}` +
      `T${pad(thirtySecsAgo.getHours())}:${pad(thirtySecsAgo.getMinutes())}:${pad(thirtySecsAgo.getSeconds())}.000`

    expect(formatDate(naive)).toBe("just now")
  })

  it('returns "N minutes ago" for a legacy naive ISO string 15 min ago', () => {
    const fifteenMinAgo = new Date(FAKE_NOW.getTime() - 15 * 60_000)
    const pad = (n: number) => String(n).padStart(2, "0")
    const naive =
      `${fifteenMinAgo.getFullYear()}-${pad(fifteenMinAgo.getMonth() + 1)}-${pad(fifteenMinAgo.getDate())}` +
      `T${pad(fifteenMinAgo.getHours())}:${pad(fifteenMinAgo.getMinutes())}:${pad(fifteenMinAgo.getSeconds())}.000`

    expect(formatDate(naive)).toBe("15 minutes ago")
  })

  // -- equivalence: same instant in different formats --

  it("produces identical output for the same instant in Z, +offset, and -offset", () => {
    // All represent the same UTC instant: 10 minutes before FAKE_NOW
    const utcZ = "2026-04-16T13:16:04.806Z"
    const plusEight = "2026-04-16T21:16:04.806+08:00"
    const minusFour = "2026-04-16T09:16:04.806-04:00"

    const resultZ = formatDate(utcZ)
    const resultPlus = formatDate(plusEight)
    const resultMinus = formatDate(minusFour)

    expect(resultZ).toBe(resultPlus)
    expect(resultZ).toBe(resultMinus)
    expect(resultZ).toBe("10 minutes ago")
  })
})

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

describe("formatters", () => {
  describe("structuredOutputModeToString", () => {
    it("should convert 'default' to 'Default (Legacy)'", () => {
      expect(structuredOutputModeToString("default")).toBe("Default (Legacy)")
    })

    it("should convert 'json_schema' to 'JSON Schema'", () => {
      expect(structuredOutputModeToString("json_schema")).toBe("JSON Schema")
    })

    it("should convert 'function_calling_weak' to 'Weak Function Calling'", () => {
      expect(structuredOutputModeToString("function_calling_weak")).toBe(
        "Weak Function Calling",
      )
    })

    it("should convert 'function_calling' to 'Function Calling'", () => {
      expect(structuredOutputModeToString("function_calling")).toBe(
        "Function Calling",
      )
    })

    it("should convert 'json_mode' to 'JSON Mode'", () => {
      expect(structuredOutputModeToString("json_mode")).toBe("JSON Mode")
    })

    it("should convert 'json_instructions' to 'JSON Instructions'", () => {
      expect(structuredOutputModeToString("json_instructions")).toBe(
        "JSON Instructions",
      )
    })

    it("should convert 'json_instruction_and_object' to 'JSON Instructions + Mode'", () => {
      expect(structuredOutputModeToString("json_instruction_and_object")).toBe(
        "JSON Instructions + Mode",
      )
    })

    it("should convert 'json_custom_instructions' to 'None'", () => {
      expect(structuredOutputModeToString("json_custom_instructions")).toBe(
        "None",
      )
    })

    it("should convert 'unknown' to 'Unknown'", () => {
      expect(structuredOutputModeToString("unknown")).toBe("Unknown")
    })

    it("should handle all valid StructuredOutputMode values", () => {
      const testCases: Array<[StructuredOutputMode, string]> = [
        ["default", "Default (Legacy)"],
        ["json_schema", "JSON Schema"],
        ["function_calling_weak", "Weak Function Calling"],
        ["function_calling", "Function Calling"],
        ["json_mode", "JSON Mode"],
        ["json_instructions", "JSON Instructions"],
        ["json_instruction_and_object", "JSON Instructions + Mode"],
        ["json_custom_instructions", "None"],
        ["unknown", "Unknown"],
      ]

      testCases.forEach(([mode, expected]) => {
        expect(structuredOutputModeToString(mode)).toBe(expected)
      })
    })
  })
})

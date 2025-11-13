import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { generate_eval_tag } from "./eval_utils"

describe("generate_eval_tag", () => {
  beforeEach(() => {
    vi.spyOn(Math, "random")
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("converts normal names to lowercase with underscores", () => {
    const result = generate_eval_tag("Test Name")
    expect(result).toBe("test_name")
  })

  it("handles single words without spaces", () => {
    const result = generate_eval_tag("TestName")
    expect(result).toBe("testname")
  })

  it("handles multiple spaces", () => {
    const result = generate_eval_tag("Test   Multiple   Spaces")
    expect(result).toBe("test___multiple___spaces")
  })

  it("handles special characters (keeps them as is)", () => {
    const result = generate_eval_tag("Test-Name_With.Special@Chars")
    expect(result).toBe("test-name_with.special@chars")
  })

  it("handles numbers in the name", () => {
    const result = generate_eval_tag("Test 123 Name")
    expect(result).toBe("test_123_name")
  })

  it("truncates names longer than 32 characters", () => {
    const longName = "This is a very long name that exceeds the limit"
    const result = generate_eval_tag(longName)
    expect(result).toBe("this_is_a_very_long_name_that_ex")
    expect(result.length).toBe(32)
  })

  it("handles exactly 32 character names", () => {
    const exactName = "This name is exactly thirty-two!" // 32 chars
    const result = generate_eval_tag(exactName)
    expect(result).toBe("this_name_is_exactly_thirty-two!")
    expect(result.length).toBe(32)
  })

  it("handles names shorter than 32 characters", () => {
    const shortName = "Short Name"
    const result = generate_eval_tag(shortName)
    expect(result).toBe("short_name")
    expect(result.length).toBeLessThan(32)
  })

  it("generates random tag when name is empty string", () => {
    // Mock Math.random to return 0.5, which should give us the middle value
    vi.mocked(Math.random).mockReturnValue(0.5)

    const result = generate_eval_tag("")
    expect(result).toBe("eval_55000") // 10000 + floor(0.5 * 90000) = 10000 + 45000 = 55000
  })

  it("generates random tag with minimum value when Math.random returns 0", () => {
    vi.mocked(Math.random).mockReturnValue(0)

    const result = generate_eval_tag("")
    expect(result).toBe("eval_10000")
  })

  it("generates random tag with maximum value when Math.random returns close to 1", () => {
    vi.mocked(Math.random).mockReturnValue(0.999999)

    const result = generate_eval_tag("")
    expect(result).toBe("eval_99999")
  })

  it("handles whitespace-only names (they become underscores, not random)", () => {
    const result = generate_eval_tag("   ")
    expect(result).toBe("___")
  })

  it("handles mixed whitespace and characters", () => {
    const result = generate_eval_tag("  test  name  ")
    expect(result).toBe("__test__name__")
  })

  it("preserves underscores in original names", () => {
    const result = generate_eval_tag("Test_Name_With_Underscores")
    expect(result).toBe("test_name_with_underscores")
  })

  it("handles Unicode characters", () => {
    const result = generate_eval_tag("Test Café Naïve")
    expect(result).toBe("test_café_naïve")
  })

  it("handles mixed case with numbers and spaces", () => {
    const result = generate_eval_tag("API Test 2024 Version")
    expect(result).toBe("api_test_2024_version")
  })

  it("generates different random values on multiple calls with empty string", () => {
    vi.mocked(Math.random).mockReturnValueOnce(0.1).mockReturnValueOnce(0.9)

    const result1 = generate_eval_tag("")
    const result2 = generate_eval_tag("")

    expect(result1).toBe("eval_19000") // 10000 + floor(0.1 * 90000) = 10000 + 9000 = 19000
    expect(result2).toBe("eval_91000") // 10000 + floor(0.9 * 90000) = 10000 + 81000 = 91000
    expect(result1).not.toBe(result2)
  })

  it("only generates random tags for truly empty strings", () => {
    vi.mocked(Math.random).mockReturnValue(0.5)

    // These should NOT generate random tags
    expect(generate_eval_tag(" ")).toBe("_")
    expect(generate_eval_tag("_")).toBe("_")
    expect(generate_eval_tag("a")).toBe("a")

    // Only this should generate a random tag
    expect(generate_eval_tag("")).toBe("eval_55000")
  })
})

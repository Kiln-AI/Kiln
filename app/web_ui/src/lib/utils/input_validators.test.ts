import { describe, it, expect } from "vitest"
import {
  validate_number,
  number_validator,
  tool_name_validator,
} from "./input_validators"

describe("input_validators", () => {
  describe("validate_number", () => {
    const defaultOptions = {
      min: 0,
      max: 100,
      integer: false,
      label: "Test Field",
      optional: false,
    }

    describe("required field validation", () => {
      it("should return error when required field is null", () => {
        const result = validate_number(null, defaultOptions)
        expect(result).toBe('"Test Field" is required')
      })

      it("should return error when required field is undefined", () => {
        const result = validate_number(undefined, defaultOptions)
        expect(result).toBe('"Test Field" is required')
      })

      it("should return error when required field is empty string", () => {
        const result = validate_number("", defaultOptions)
        expect(result).toBe('"Test Field" is required')
      })

      it("should return error when required field is whitespace string", () => {
        const result = validate_number("   ", defaultOptions)
        expect(result).toBe('"Test Field" is required')
      })
    })

    describe("optional field validation", () => {
      const optionalOptions = {
        min: 0,
        max: 100,
        integer: false,
        label: "Test Field",
        optional: true,
      }

      it("should return null when optional field is null", () => {
        const result = validate_number(null, optionalOptions)
        expect(result).toBe(null)
      })

      it("should return null when optional field is undefined", () => {
        const result = validate_number(undefined, optionalOptions)
        expect(result).toBe(null)
      })

      it("should return null when optional field is empty string", () => {
        const result = validate_number("", optionalOptions)
        expect(result).toBe(null)
      })

      it("should return null when optional field is whitespace string", () => {
        const result = validate_number("   ", optionalOptions)
        expect(result).toBe(null)
      })
    })

    describe("string input validation", () => {
      it("should accept valid numeric string", () => {
        const result = validate_number("42", defaultOptions)
        expect(result).toBe(null)
      })

      it("should accept valid decimal string", () => {
        const result = validate_number("42.5", defaultOptions)
        expect(result).toBe(null)
      })

      it("should return error for invalid numeric string", () => {
        const result = validate_number("not-a-number", defaultOptions)
        expect(result).toBe("Please enter a valid number")
      })

      it("should return error for string with letters", () => {
        const result = validate_number("123abc", defaultOptions)
        expect(result).toBe("Test Field must be less than 100")
      })

      it("should accept string with leading/trailing spaces", () => {
        const result = validate_number("  42  ", defaultOptions)
        expect(result).toBe(null)
      })
    })

    describe("number input validation", () => {
      it("should accept valid number", () => {
        const result = validate_number(42, defaultOptions)
        expect(result).toBe(null)
      })

      it("should accept valid decimal number", () => {
        const result = validate_number(42.5, defaultOptions)
        expect(result).toBe(null)
      })

      it("should accept zero", () => {
        const result = validate_number(0, defaultOptions)
        expect(result).toBe(null)
      })

      it("should accept negative number within range", () => {
        const result = validate_number(-10, {
          min: -20,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })
    })

    describe("integer validation", () => {
      const integerOptions = {
        min: 0,
        max: 100,
        integer: true,
        label: "Test Field",
        optional: false,
      }

      it("should accept valid integer string", () => {
        const result = validate_number("42", integerOptions)
        expect(result).toBe(null)
      })

      it("should return error for decimal string when integer required", () => {
        const result = validate_number("42.5", integerOptions)
        expect(result).toBe("Test Field must be an integer")
      })

      it("should accept decimal number when integer required (only strings are checked)", () => {
        const result = validate_number(42.5, integerOptions)
        expect(result).toBe(null)
      })

      it("should only validate integer constraint for string inputs, not number inputs", () => {
        // String input with decimal should fail integer validation
        const stringResult = validate_number("42.5", integerOptions)
        expect(stringResult).toBe("Test Field must be an integer")

        // Number input with decimal should pass (integer validation only applies to strings)
        const numberResult = validate_number(42.5, integerOptions)
        expect(numberResult).toBe(null)
      })

      it("should accept valid integer number", () => {
        const result = validate_number(42, integerOptions)
        expect(result).toBe(null)
      })
    })

    describe("range validation", () => {
      it("should return error when value is below minimum", () => {
        const result = validate_number(5, {
          min: 10,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe("Test Field must be greater than 10")
      })

      it("should return error when value is above maximum", () => {
        const result = validate_number(150, {
          min: 0,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe("Test Field must be less than 100")
      })

      it("should accept value at minimum boundary", () => {
        const result = validate_number(10, {
          min: 10,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })

      it("should accept value at maximum boundary", () => {
        const result = validate_number(100, {
          min: 0,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })

      it("should accept value within range", () => {
        const result = validate_number(50, {
          min: 0,
          max: 100,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })
    })

    describe("edge cases", () => {
      it("should return error for boolean input", () => {
        const result = validate_number(true, defaultOptions)
        expect(result).toBe("Please enter a valid number")
      })

      it("should return error for object input", () => {
        const result = validate_number({}, defaultOptions)
        expect(result).toBe("Please enter a valid number")
      })

      it("should return error for array input", () => {
        const result = validate_number([1, 2, 3], defaultOptions)
        expect(result).toBe("Please enter a valid number")
      })

      it("should handle negative range", () => {
        const result = validate_number(-5, {
          min: -10,
          max: -1,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })

      it("should handle zero range", () => {
        const result = validate_number(0, {
          min: 0,
          max: 0,
          integer: false,
          label: "Test Field",
          optional: false,
        })
        expect(result).toBe(null)
      })
    })

    describe("custom label handling", () => {
      it("should use custom label in error messages", () => {
        const result = validate_number("", {
          min: 0,
          max: 100,
          integer: false,
          label: "Custom Label",
          optional: false,
        })
        expect(result).toBe('"Custom Label" is required')
      })

      it("should use custom label in range error messages", () => {
        const result = validate_number(150, {
          min: 0,
          max: 100,
          integer: false,
          label: "Custom Label",
          optional: false,
        })
        expect(result).toBe("Custom Label must be less than 100")
      })

      it("should use custom label in integer error messages", () => {
        const result = validate_number("42.5", {
          min: 0,
          max: 100,
          integer: true,
          label: "Custom Label",
          optional: false,
        })
        expect(result).toBe("Custom Label must be an integer")
      })
    })
  })

  describe("number_validator", () => {
    it("should create a validator function with the specified options", () => {
      const validator = number_validator({
        min: 10,
        max: 100,
        integer: true,
        label: "Test Field",
        optional: false,
      })

      expect(validator(5)).toBe("Test Field must be greater than 10")
      expect(validator(150)).toBe("Test Field must be less than 100")
      expect(validator("42.5")).toBe("Test Field must be an integer")
      expect(validator(50)).toBe(null)
    })

    it("should handle optional fields correctly", () => {
      const validator = number_validator({
        min: 0,
        max: 100,
        integer: false,
        label: "Optional Field",
        optional: true,
      })

      expect(validator(null)).toBe(null)
      expect(validator("")).toBe(null)
      expect(validator(50)).toBe(null)
    })

    it("should handle undefined min/max values", () => {
      const validator = number_validator({
        label: "Unbounded Field",
        optional: false,
      })

      expect(validator(50)).toBe(null)
      expect(validator(-50)).toBe(null)
      expect(validator(1000)).toBe(null)
    })

    it("should properly handle zero as min value", () => {
      const validator = number_validator({
        min: 0,
        label: "Zero Min Field",
        optional: false,
      })

      expect(validator(-1)).toBe("Zero Min Field must be greater than 0")
      expect(validator(0)).toBe(null)
      expect(validator(1)).toBe(null)
      expect(validator(100)).toBe(null)
    })

    it("should properly handle zero as max value", () => {
      const validator = number_validator({
        max: 0,
        label: "Zero Max Field",
        optional: false,
      })

      expect(validator(-100)).toBe(null)
      expect(validator(-1)).toBe(null)
      expect(validator(0)).toBe(null)
      expect(validator(1)).toBe("Zero Max Field must be less than 0")
      expect(validator(100)).toBe("Zero Max Field must be less than 0")
    })

    it("should properly handle zero as both min and max values", () => {
      const validator = number_validator({
        min: 0,
        max: 0,
        label: "Zero Range Field",
        optional: false,
      })

      expect(validator(-1)).toBe("Zero Range Field must be greater than 0")
      expect(validator(0)).toBe(null)
      expect(validator(1)).toBe("Zero Range Field must be less than 0")
    })

    it("should distinguish between zero and undefined boundaries", () => {
      // Test with no boundaries (undefined min/max)
      const unboundedValidator = number_validator({
        label: "Unbounded Field",
        optional: false,
      })

      // Test with zero boundaries
      const zeroBoundedValidator = number_validator({
        min: 0,
        max: 0,
        label: "Zero Bounded Field",
        optional: false,
      })

      // Unbounded should accept any value
      expect(unboundedValidator(-100)).toBe(null)
      expect(unboundedValidator(0)).toBe(null)
      expect(unboundedValidator(100)).toBe(null)

      // Zero bounded should only accept 0
      expect(zeroBoundedValidator(-100)).toBe(
        "Zero Bounded Field must be greater than 0",
      )
      expect(zeroBoundedValidator(0)).toBe(null)
      expect(zeroBoundedValidator(100)).toBe(
        "Zero Bounded Field must be less than 0",
      )
    })
  })

  describe("tool_name_validator", () => {
    describe("empty value validation", () => {
      it("should return error for null", () => {
        const result = tool_name_validator(null)
        expect(result).toBe("Cannot be empty")
      })

      it("should return error for undefined", () => {
        const result = tool_name_validator(undefined)
        expect(result).toBe("Cannot be empty")
      })

      it("should return error for empty string", () => {
        const result = tool_name_validator("")
        expect(result).toBe("Cannot be empty")
      })

      it("should return error for whitespace string", () => {
        const result = tool_name_validator("   ")
        expect(result).toBe("Cannot be empty")
      })
    })

    describe("type validation", () => {
      it("should return error for number input", () => {
        const result = tool_name_validator(123)
        expect(result).toBe("Must be a string")
      })

      it("should return error for boolean input", () => {
        const result = tool_name_validator(true)
        expect(result).toBe("Must be a string")
      })

      it("should return error for object input", () => {
        const result = tool_name_validator({})
        expect(result).toBe("Must be a string")
      })

      it("should return error for array input", () => {
        const result = tool_name_validator([])
        expect(result).toBe("Must be a string")
      })
    })

    describe("valid snake_case validation", () => {
      it("should accept simple lowercase name", () => {
        const result = tool_name_validator("tool")
        expect(result).toBe(null)
      })

      it("should accept name with numbers", () => {
        const result = tool_name_validator("tool123")
        expect(result).toBe(null)
      })

      it("should accept name with underscores", () => {
        const result = tool_name_validator("my_tool")
        expect(result).toBe(null)
      })

      it("should accept complex valid snake_case", () => {
        const result = tool_name_validator("my_tool_123_name")
        expect(result).toBe(null)
      })

      it("should not allow leading/trailing whitespace", () => {
        const result = tool_name_validator("  my_tool  ")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })
    })

    describe("invalid character validation", () => {
      it("should return error for uppercase letters", () => {
        const result = tool_name_validator("MyTool")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })

      it("should return error for hyphens", () => {
        const result = tool_name_validator("my-tool")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })

      it("should return error for spaces", () => {
        const result = tool_name_validator("my tool")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })

      it("should return error for special characters", () => {
        const result = tool_name_validator("my@tool")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })

      it("should return error for dots", () => {
        const result = tool_name_validator("my.tool")
        expect(result).toBe(
          "Must be in snake_case: containing only lowercase letters (a-z), numbers (0-9), and underscores",
        )
      })
    })

    describe("underscore position validation", () => {
      it("should return error for name starting with underscore", () => {
        const result = tool_name_validator("_tool")
        expect(result).toBe("Cannot start or end with an underscore")
      })

      it("should return error for name ending with underscore", () => {
        const result = tool_name_validator("tool_")
        expect(result).toBe("Cannot start or end with an underscore")
      })

      it("should return error for name starting and ending with underscore", () => {
        const result = tool_name_validator("_tool_")
        expect(result).toBe("Cannot start or end with an underscore")
      })
    })

    describe("consecutive underscore validation", () => {
      it("should return error for double underscores", () => {
        const result = tool_name_validator("my__tool")
        expect(result).toBe("Cannot contain consecutive underscores")
      })

      it("should return error for triple underscores", () => {
        const result = tool_name_validator("my___tool")
        expect(result).toBe("Cannot contain consecutive underscores")
      })

      it("should return error for multiple double underscores", () => {
        const result = tool_name_validator("my__tool__name")
        expect(result).toBe("Cannot contain consecutive underscores")
      })
    })

    describe("starting character validation", () => {
      it("should return error for name starting with number", () => {
        const result = tool_name_validator("1tool")
        expect(result).toBe("Must start with a lowercase letter")
      })

      it("should return error for name starting with underscore (covered by underscore position rule)", () => {
        const result = tool_name_validator("_tool")
        expect(result).toBe("Cannot start or end with an underscore")
      })

      it("should accept name starting with lowercase letter", () => {
        const result = tool_name_validator("atool")
        expect(result).toBe(null)
      })
    })

    describe("edge cases", () => {
      it("should accept single letter", () => {
        const result = tool_name_validator("a")
        expect(result).toBe(null)
      })

      it("should accept single letter with number", () => {
        const result = tool_name_validator("a1")
        expect(result).toBe(null)
      })

      it("should return error for single underscore", () => {
        const result = tool_name_validator("_")
        expect(result).toBe("Cannot start or end with an underscore")
      })

      it("should return error for single number", () => {
        const result = tool_name_validator("1")
        expect(result).toBe("Must start with a lowercase letter")
      })

      it("should return error for name longer than 64 characters", () => {
        const result = tool_name_validator("a".repeat(65))
        expect(result).toBe("Must be less than 65 characters long")
      })
    })
  })
})

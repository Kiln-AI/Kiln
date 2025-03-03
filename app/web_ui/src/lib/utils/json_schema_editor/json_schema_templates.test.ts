import {
  string_to_json_key,
  schema_from_model,
  model_from_schema,
  typed_json_from_schema_model,
} from "./json_schema_templates"
import type { SchemaModel, JsonSchema } from "./json_schema_templates"
import { describe, it, expect } from "vitest"
import { KilnError } from "$lib/utils/error_handlers"

describe("string_to_json_key", () => {
  it("converts spaces to underscores", () => {
    expect(string_to_json_key("Hello World")).toBe("hello_world")
  })

  it("converts to lowercase", () => {
    expect(string_to_json_key("UPPERCASE")).toBe("uppercase")
  })

  it("removes special characters", () => {
    expect(string_to_json_key("Special@#$Characters!")).toBe(
      "specialcharacters",
    )
  })

  it("keeps alphanumeric characters, underscores, and dots", () => {
    expect(string_to_json_key("alpha123_numeric.test")).toBe(
      "alpha123_numeric.test",
    )
  })

  it("handles empty string", () => {
    expect(string_to_json_key("")).toBe("")
  })

  it("handles string with only special characters", () => {
    expect(string_to_json_key("@#$%^&*")).toBe("")
  })

  it("handles mixed case and special characters", () => {
    expect(string_to_json_key("User Name (Display)")).toBe("user_name_display")
  })

  it("handles leading and trailing spaces", () => {
    expect(string_to_json_key("  Trim Me  ")).toBe("trim_me")
  })
})

describe("schema_from_model", () => {
  it("converts a simple SchemaModel to JsonSchema", () => {
    const model: SchemaModel = {
      properties: [
        {
          id: "user_name",
          title: "User Name",
          description: "The user's full name",
          type: "string",
          required: true,
        },
        {
          id: "age",
          title: "Age",
          description: "User's age in years",
          type: "integer",
          required: false,
        },
      ],
    }

    const expected: JsonSchema = {
      type: "object",
      properties: {
        user_name: {
          title: "User Name",
          type: "string",
          description: "The user's full name",
        },
        age: {
          title: "Age",
          type: "integer",
          description: "User's age in years",
        },
      },
      required: ["user_name"],
    }

    expect(schema_from_model(model, true)).toEqual(expected)
  })

  it("handles empty SchemaModel", () => {
    const model: SchemaModel = {
      properties: [],
    }

    const expected: JsonSchema = {
      type: "object",
      properties: {},
      required: [],
    }

    expect(schema_from_model(model, true)).toEqual(expected)
  })

  it("correctly handles required fields", () => {
    const model: SchemaModel = {
      properties: [
        {
          id: "field1",
          title: "Field1",
          description: "Description 1",
          type: "string",
          required: true,
        },
        {
          id: "field2",
          title: "Field2",
          description: "Description 2",
          type: "number",
          required: false,
        },
        {
          id: "field3",
          title: "Field3",
          description: "Description 3",
          type: "boolean",
          required: true,
        },
      ],
    }

    const result = schema_from_model(model, true)
    expect(result.required).toEqual(["field1", "field3"])
  })

  it("correctly converts property titles to names", () => {
    const model: SchemaModel = {
      properties: [
        {
          id: "user_name",
          title: "User Name",
          description: "Full name",
          type: "string",
          required: true,
        },
        {
          id: "email_address",
          title: "Email Address",
          description: "Contact email",
          type: "string",
          required: true,
        },
      ],
    }

    const result = schema_from_model(model, true)
    expect(Object.keys(result.properties)).toEqual([
      "user_name",
      "email_address",
    ])
  })

  it("preserves property IDs when creating=false, even if titles change", () => {
    const model: SchemaModel = {
      properties: [
        {
          id: "original_id",
          title: "Changed Title",
          description: "Some description",
          type: "string",
          required: true,
        },
        {
          id: "another_id",
          title: "Another Changed Title",
          description: "Another description",
          type: "number",
          required: false,
        },
      ],
    }

    const result = schema_from_model(model, false)

    // Check that the property keys match the original IDs, not the new titles
    expect(Object.keys(result.properties)).toEqual([
      "original_id",
      "another_id",
    ])

    // Verify the titles were updated while IDs were preserved
    expect(result.properties["original_id"].title).toBe("Changed Title")
    expect(result.properties["another_id"].title).toBe("Another Changed Title")
    expect(result.required).toEqual(["original_id"])
  })
})

describe("model_from_schema", () => {
  it("converts a simple JsonSchema to SchemaModel", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        user_name: {
          title: "User Name",
          type: "string",
          description: "The user's full name",
        },
        age: {
          title: "Age",
          type: "integer",
          description: "User's age in years",
        },
      },
      required: ["user_name"],
    }

    const expected: SchemaModel = {
      properties: [
        {
          id: "user_name",
          title: "User Name",
          description: "The user's full name",
          type: "string",
          required: true,
        },
        {
          id: "age",
          title: "Age",
          description: "User's age in years",
          type: "integer",
          required: false,
        },
      ],
    }

    expect(model_from_schema(schema)).toEqual(expected)
  })

  it("handles empty JsonSchema", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {},
      required: [],
    }

    const expected: SchemaModel = {
      properties: [],
    }

    expect(model_from_schema(schema)).toEqual(expected)
  })

  it("correctly handles required fields", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        field1: {
          title: "Field1",
          type: "string",
          description: "Description 1",
        },
        field2: {
          title: "Field2",
          type: "number",
          description: "Description 2",
        },
        field3: {
          title: "Field3",
          type: "boolean",
          description: "Description 3",
        },
      },
      required: ["field1", "field3"],
    }

    const result = model_from_schema(schema)
    expect(
      result.properties.filter((p) => p.required).map((p) => p.title),
    ).toEqual(["Field1", "Field3"])
  })

  it("uses property name as title when title is not provided", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        // @ts-expect-error -- title is missing to test this case
        user_name: {
          type: "string",
          description: "The user's name",
        },
      },
      required: [],
    }

    const result = model_from_schema(schema)
    expect(result.properties[0].title).toBe("user_name")
  })
})

describe("typed_json_from_schema_model", () => {
  const testSchema: SchemaModel = {
    properties: [
      {
        id: "name",
        title: "Name",
        description: "User's name",
        type: "string",
        required: true,
      },
      {
        id: "age",
        title: "Age",
        description: "User's age",
        type: "integer",
        required: true,
      },
      {
        id: "height",
        title: "Height",
        description: "User's height in meters",
        type: "number",
        required: false,
      },
      {
        id: "is_active",
        title: "Is Active",
        description: "User's active status",
        type: "boolean",
        required: false,
      },
    ],
  }

  it("correctly parses valid input data", () => {
    const inputData = {
      name: "John Doe",
      age: "30",
      height: "1.75",
      is_active: "true",
    }

    const result = typed_json_from_schema_model(testSchema, inputData)

    expect(result).toEqual({
      name: "John Doe",
      age: 30,
      height: 1.75,
      is_active: true,
    })
  })

  it("handles missing optional properties", () => {
    const inputData = {
      name: "Jane Doe",
      age: "25",
    }

    const result = typed_json_from_schema_model(testSchema, inputData)

    expect(result).toEqual({
      name: "Jane Doe",
      age: 25,
    })
  })

  it("throws error for invalid integer", () => {
    const inputData = {
      name: "Alice",
      age: "not a number",
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("throws error for invalid boolean", () => {
    const inputData = {
      name: "Bob",
      age: "40",
      is_active: "not a boolean",
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("throws error for unknown property", () => {
    const inputData = {
      name: "Charlie",
      age: "35",
      unknown_prop: "some value",
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("correctly parses zero values", () => {
    const inputData = {
      name: "Zero",
      age: "0",
      height: "0",
    }

    const result = typed_json_from_schema_model(testSchema, inputData)

    expect(result).toEqual({
      name: "Zero",
      age: 0,
      height: 0,
    })
  })

  it("throws error for missing required property", () => {
    const inputData = {
      name: "Alice",
      // age is missing, but it's required
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("throws error for empty string in required property", () => {
    const inputData = {
      name: "Bob",
      age: "", // Empty string for required integer
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("allows empty string for optional properties", () => {
    const inputData = {
      name: "Charlie",
      age: "30",
      height: "", // Empty string for number
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })

  it("throws error when all required properties are missing", () => {
    const inputData = {
      // Both name and age are missing
      height: "1.75",
      is_active: "true",
    }

    expect(() => typed_json_from_schema_model(testSchema, inputData)).toThrow(
      KilnError,
    )
  })
})

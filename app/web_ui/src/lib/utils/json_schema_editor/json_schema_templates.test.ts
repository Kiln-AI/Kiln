import {
  string_to_json_key,
  schema_from_model,
  model_from_schema,
} from "./json_schema_templates"
import type {
  JsonSchemaProperty,
  SchemaModelProperty,
} from "./json_schema_templates"
import { describe, it, expect } from "vitest"

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
  it("converts a simple SchemaModelProperty to JsonSchema", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
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

    const expected: JsonSchemaProperty = {
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
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
      properties: [],
    }

    const expected: JsonSchemaProperty = {
      type: "object",
      properties: {},
      required: [],
    }

    expect(schema_from_model(model, true)).toEqual(expected)
  })

  it("correctly handles required fields", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
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
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
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
    expect(Object.keys(result.properties!)).toEqual([
      "user_name",
      "email_address",
    ])
  })

  it("preserves property IDs when creating=false, even if titles change", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
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
    expect(Object.keys(result.properties!)).toEqual([
      "original_id",
      "another_id",
    ])

    // Verify the titles were updated while IDs were preserved
    expect(result.properties!["original_id"].title).toBe("Changed Title")
    expect(result.properties!["another_id"].title).toBe("Another Changed Title")
    expect(result.required).toEqual(["original_id"])
  })

  it("converts nested object properties to schema correctly", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
      properties: [
        {
          id: "user",
          title: "User",
          description: "User information",
          type: "object",
          required: true,
          additionalProperties: false,
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
              required: false,
            },
          ],
        },
      ],
    }

    const result = schema_from_model(model, false)

    expect(result.properties!["user"]).toBeDefined()
    expect(result.properties!["user"].type).toBe("object")
    expect(result.properties!["user"].properties).toBeDefined()
    expect(result.properties!["user"].additionalProperties).toBe(false)

    const userProps = result.properties!["user"].properties!
    expect(Object.keys(userProps)).toEqual(["name", "age"])
    expect(userProps["name"].title).toBe("Name")
    expect(userProps["name"].type).toBe("string")
    expect(userProps["age"].title).toBe("Age")
    expect(userProps["age"].type).toBe("integer")

    expect(result.properties!["user"].required).toEqual(["name"])
    expect(result.required).toEqual(["user"])
  })

  it("handles multiple levels of nesting when converting to schema", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
      properties: [
        {
          id: "company",
          title: "Company",
          description: "Company information",
          type: "object",
          required: false,
          properties: [
            {
              id: "name",
              title: "Company Name",
              description: "Name of the company",
              type: "string",
              required: true,
            },
            {
              id: "address",
              title: "Address",
              description: "Company address",
              type: "object",
              required: true,
              properties: [
                {
                  id: "street",
                  title: "Street",
                  description: "Street address",
                  type: "string",
                  required: false,
                },
                {
                  id: "city",
                  title: "City",
                  description: "City name",
                  type: "string",
                  required: true,
                },
              ],
            },
          ],
        },
      ],
    }

    const result = schema_from_model(model, false)

    expect(result.properties!["company"]).toBeDefined()
    expect(result.properties!["company"].type).toBe("object")

    const companyProps = result.properties!["company"].properties!
    expect(companyProps["address"]).toBeDefined()
    expect(companyProps["address"].type).toBe("object")

    const addressProps = companyProps["address"].properties!
    expect(Object.keys(addressProps)).toEqual(["street", "city"])
    expect(addressProps["city"].title).toBe("City")
    expect(addressProps["street"].title).toBe("Street")

    expect(companyProps["address"].required).toEqual(["city"])
    expect(result.properties!["company"].required).toEqual(["name", "address"])
  })

  it("preserves additionalProperties in nested objects", () => {
    const model: SchemaModelProperty = {
      type: "object",
      id: "root",
      title: "root",
      required: true,
      properties: [
        {
          id: "config",
          title: "Config",
          description: "Configuration object",
          type: "object",
          required: true,
          additionalProperties: true,
          properties: [
            {
              id: "nested",
              title: "Nested Config",
              description: "Nested configuration",
              type: "object",
              required: false,
              additionalProperties: false,
              properties: [
                {
                  id: "value",
                  title: "Value",
                  description: "A value",
                  type: "string",
                  required: false,
                },
              ],
            },
          ],
        },
      ],
      additionalProperties: false,
    }

    const result = schema_from_model(model, false)

    expect(result.additionalProperties).toBe(false)
    expect(result.properties!["config"].additionalProperties).toBe(true)
    expect(
      result.properties!["config"].properties!["nested"].additionalProperties,
    ).toBe(false)
  })

  it("round-trip conversion preserves nested structure", () => {
    const originalSchema: JsonSchemaProperty = {
      type: "object",
      properties: {
        person: {
          title: "Person",
          description: "Person information",
          type: "object",
          properties: {
            name: {
              title: "Name",
              description: "Person's name",
              type: "string",
            },
            contact: {
              title: "Contact",
              description: "Contact information",
              type: "object",
              properties: {
                email: {
                  title: "Email",
                  description: "Email address",
                  type: "string",
                },
                phone: {
                  title: "Phone",
                  description: "Phone number",
                  type: "string",
                },
              },
              required: ["email"],
              additionalProperties: false,
            },
          },
          required: ["name", "contact"],
          additionalProperties: true,
        },
      },
      required: ["person"],
      additionalProperties: false,
    }

    const model = model_from_schema(originalSchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(originalSchema)
  })
})

describe("model_from_schema", () => {
  it("converts a simple JsonSchema to SchemaModel", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      additionalProperties: false,
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
        contact_emails: {
          title: "Contact Emails",
          type: "array",
          description: "The user's contact emails",
          items: {
            type: "string",
            title: "Contact Email",
            description: "The user's contact email",
            items: {
              type: "string",
              title: "Email",
              description: "The user's email",
            },
          },
        },
        siblings: {
          title: "Siblings",
          type: "array",
          description: "The user's siblings",
          items: {
            title: "Sibling",
            description: "A sibling object",
            type: "object",
            properties: {
              name: {
                type: "string",
                title: "Name",
                description: "The user's name",
              },
              age: {
                type: "integer",
                title: "Age",
                description: "The user's age",
              },
            },
            required: ["name", "age"],
          },
        },
      },
      required: ["user_name"],
    }

    const expected: SchemaModelProperty = {
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
        {
          id: "contact_emails",
          title: "Contact Emails",
          description: "The user's contact emails",
          type: "array",
          required: false,
          items: {
            id: "items",
            title: "Contact Email",
            description: "The user's contact email",
            type: "string",
            required: false,
          },
        },
        {
          id: "siblings",
          title: "Siblings",
          description: "The user's siblings",
          type: "array",
          required: false,
          items: {
            id: "items",
            title: "Sibling",
            description: "A sibling object",
            type: "object",
            required: false,
            properties: [
              {
                id: "name",
                title: "Name",
                description: "The user's name",
                type: "string",
                required: true,
              },
              {
                id: "age",
                title: "Age",
                description: "The user's age",
                type: "integer",
                required: true,
              },
            ],
          },
        },
      ],
      additionalProperties: false,
      id: "root",
      title: "root",
      description: undefined,
      type: "object",
      required: true,
    }

    expect(model_from_schema(schema)).toEqual(expected)
  })

  it("handles empty JsonSchema", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      additionalProperties: false,
      properties: {},
      required: [],
    }

    const expected: SchemaModelProperty = {
      properties: [],
      id: "root",
      title: "root",
      description: undefined,
      type: "object",
      required: true,
      additionalProperties: false,
    }

    expect(model_from_schema(schema)).toEqual(expected)
  })

  it("correctly handles required fields", () => {
    const schema: JsonSchemaProperty = {
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
        field4: {
          title: "Field4",
          type: "array",
          description: "Description 4",
        },
      },
      required: ["field1", "field3"],
    }

    const result = model_from_schema(schema)
    expect(
      result.properties!.filter((p) => p.required).map((p) => p.title),
    ).toEqual(["Field1", "Field3"])
  })

  it("uses property name as title when title is not provided", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      properties: {
        user_name: {
          type: "string",
          description: "The user's name",
        },
      },
      required: [],
    }

    const result = model_from_schema(schema)
    expect(result.properties![0].title).toBe("user_name")
  })

  it("handles array types", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      properties: {
        ingredients: {
          title: "Ingredients",
          description: "The ingredients to be used",
          type: "array",
          items: {
            type: "string",
            description: "The name of the ingredient to be used",
            title: "Ingredient",
          },
        },
      },
      required: ["ingredients"],
    }

    const result = model_from_schema(schema)
    expect(result.properties![0].type).toBe("array")
  })

  it("converts nested object properties correctly", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      properties: {
        user: {
          title: "User",
          description: "User information",
          type: "object",
          properties: {
            name: {
              title: "Name",
              description: "User's name",
              type: "string",
            },
            age: {
              title: "Age",
              description: "User's age",
              type: "integer",
            },
          },
          required: ["name"],
          additionalProperties: false,
        },
      },
      required: ["user"],
    }

    const result = model_from_schema(schema)

    expect(result.properties).toHaveLength(1)
    expect(result.properties![0].id).toBe("user")
    expect(result.properties![0].type).toBe("object")
    expect(result.properties![0].required).toBe(true)
    expect(result.properties![0].properties).toHaveLength(2)
    expect(result.properties![0].additionalProperties).toBe(false)

    const nameProperty = result.properties![0].properties![0]
    expect(nameProperty.id).toBe("name")
    expect(nameProperty.title).toBe("Name")
    expect(nameProperty.type).toBe("string")
    expect(nameProperty.required).toBe(true)

    const ageProperty = result.properties![0].properties![1]
    expect(ageProperty.id).toBe("age")
    expect(ageProperty.title).toBe("Age")
    expect(ageProperty.type).toBe("integer")
    expect(ageProperty.required).toBe(false)
  })

  it("handles multiple levels of nesting", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      properties: {
        company: {
          title: "Company",
          description: "Company information",
          type: "object",
          properties: {
            name: {
              title: "Company Name",
              description: "Name of the company",
              type: "string",
            },
            address: {
              title: "Address",
              description: "Company address",
              type: "object",
              properties: {
                street: {
                  title: "Street",
                  description: "Street address",
                  type: "string",
                },
                city: {
                  title: "City",
                  description: "City name",
                  type: "string",
                },
              },
              required: ["city"],
            },
          },
          required: ["name", "address"],
        },
      },
      required: [],
    }

    const result = model_from_schema(schema)

    expect(result.properties).toHaveLength(1)
    const companyProp = result.properties![0]
    expect(companyProp.type).toBe("object")
    expect(companyProp.properties).toHaveLength(2)

    const addressProp = companyProp.properties![1]
    expect(addressProp.id).toBe("address")
    expect(addressProp.type).toBe("object")
    expect(addressProp.properties).toHaveLength(2)

    const cityProp = addressProp.properties![1]
    expect(cityProp.id).toBe("city")
    expect(cityProp.required).toBe(true)

    const streetProp = addressProp.properties![0]
    expect(streetProp.id).toBe("street")
    expect(streetProp.required).toBe(false)
  })

  it("doesn't modify additionalProperties when not specified for nested objects", () => {
    const schema: JsonSchemaProperty = {
      type: "object",
      properties: {
        config: {
          title: "Config",
          description: "Configuration object",
          type: "object",
          properties: {
            setting: {
              title: "Setting",
              description: "A setting",
              type: "string",
            },
          },
        },
      },
      required: [],
    }

    const result = model_from_schema(schema)
    expect(result.properties![0].additionalProperties).toBe(undefined)
  })
})

// Our best tests. Converts from JSON schema, to internal model, and back. Catches the widest range of possible issues.
describe("round-trip conversion tests", () => {
  it("preserves a complex real-world schema through model conversion", () => {
    const complexSchema: JsonSchemaProperty = {
      type: "object",
      properties: {
        userId: {
          title: "User ID",
          description: "Unique identifier for the user",
          type: "string",
        },
        profile: {
          title: "Profile",
          description: "User profile information",
          type: "object",
          properties: {
            firstName: {
              title: "First Name",
              description: "User's first name",
              type: "string",
            },
            lastName: {
              title: "Last Name",
              description: "User's last name",
              type: "string",
            },
            age: {
              title: "Age",
              description: "User's age in years",
              type: "integer",
            },
            height: {
              title: "Height",
              description: "User's height in meters",
              type: "number",
            },
            isVerified: {
              title: "Is Verified",
              description: "Whether the user is verified",
              type: "boolean",
            },
            address: {
              title: "Address",
              description: "User's address",
              type: "object",
              properties: {
                street: {
                  title: "Street",
                  description: "Street address",
                  type: "string",
                },
                city: {
                  title: "City",
                  description: "City name",
                  type: "string",
                },
                postalCode: {
                  title: "Postal Code",
                  description: "Postal/ZIP code",
                  type: "string",
                },
                coordinates: {
                  title: "Coordinates",
                  description: "GPS coordinates",
                  type: "object",
                  properties: {
                    latitude: {
                      title: "Latitude",
                      description: "Latitude coordinate",
                      type: "number",
                    },
                    longitude: {
                      title: "Longitude",
                      description: "Longitude coordinate",
                      type: "number",
                    },
                  },
                  required: ["latitude", "longitude"],
                  additionalProperties: false,
                },
              },
              required: ["city", "postalCode"],
              additionalProperties: true,
            },
          },
          required: ["firstName", "lastName", "age"],
          additionalProperties: false,
        },
        tags: {
          title: "Tags",
          description: "User tags",
          type: "array",
        },
        preferences: {
          title: "Preferences",
          description: "User preferences",
          type: "object",
          properties: {
            notifications: {
              title: "Notifications",
              description: "Notification settings",
              type: "boolean",
            },
            theme: {
              title: "Theme",
              description: "UI theme preference",
              type: "string",
            },
          },
          required: [],
          additionalProperties: true,
        },
        phoneNumbers: {
          title: "Phone Numbers",
          description: "Contact phone numbers",
          type: "array",
        },
        metadata: {
          title: "Metadata",
          description: "Additional metadata",
          type: "object",
          properties: {},
          required: [],
          additionalProperties: true,
        },
      },
      required: ["userId", "profile", "tags"],
      additionalProperties: false,
    }

    const model = model_from_schema(complexSchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(complexSchema)
  })

  it("preserves array items specifications through round-trip conversion", () => {
    const arraySchema: JsonSchemaProperty = {
      type: "object",
      properties: {
        simpleStringArray: {
          title: "Simple String Array",
          description: "An array of strings",
          type: "array",
          items: {
            title: "String Item",
            description: "A string value",
            type: "string",
          },
        },
        numberArray: {
          title: "Number Array",
          description: "An array of numbers",
          type: "array",
          items: {
            title: "Number Item",
            description: "A number value",
            type: "number",
          },
        },
        objectArray: {
          title: "Object Array",
          description: "An array of complex objects",
          type: "array",
          items: {
            title: "Person",
            description: "A person object",
            type: "object",
            properties: {
              name: {
                title: "Name",
                description: "Person's name",
                type: "string",
              },
              age: {
                title: "Age",
                description: "Person's age",
                type: "integer",
              },
              active: {
                title: "Active",
                description: "Whether person is active",
                type: "boolean",
              },
            },
            required: ["name"],
            additionalProperties: false,
          },
        },
        nestedArrays: {
          title: "Nested Arrays",
          description: "An array of arrays",
          type: "array",
          items: {
            title: "Inner Array",
            description: "An inner array of integers",
            type: "array",
            items: {
              title: "Integer",
              description: "An integer value",
              type: "integer",
            },
          },
        },
        mixedRequired: {
          title: "Mixed Required Array",
          description: "A required array of optional objects",
          type: "array",
          items: {
            title: "Config",
            description: "Configuration object",
            type: "object",
            properties: {
              key: {
                title: "Key",
                description: "Config key",
                type: "string",
              },
              value: {
                title: "Value",
                description: "Config value",
                type: "string",
              },
              priority: {
                title: "Priority",
                description: "Priority level",
                type: "integer",
              },
            },
            required: ["key"],
            additionalProperties: true,
          },
        },
      },
      required: ["simpleStringArray", "mixedRequired"],
      additionalProperties: false,
    }

    const model = model_from_schema(arraySchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(arraySchema)
  })

  it("preserves an array with items at top level through round-trip conversion", () => {
    const topLevelArraySchema: JsonSchemaProperty = {
      title: "Top Level Array",
      description: "An array at the root level",
      type: "array",
      items: {
        title: "Task",
        description: "A task object",
        type: "object",
        properties: {
          id: {
            title: "ID",
            description: "Task identifier",
            type: "string",
          },
          name: {
            title: "Name",
            description: "Task name",
            type: "string",
          },
          completed: {
            title: "Completed",
            description: "Whether the task is completed",
            type: "boolean",
          },
        },
        required: ["id", "name"],
        additionalProperties: false,
      },
    }

    const model = model_from_schema(topLevelArraySchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(topLevelArraySchema)
  })

  it("preserves a basic type at top level through round-trip conversion", () => {
    const topLevelStringSchema: JsonSchemaProperty = {
      title: "Simple String",
      description: "A string value at the root level",
      type: "string",
    }

    const model = model_from_schema(topLevelStringSchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(topLevelStringSchema)
  })

  it("preserves enum properties through round-trip conversion", () => {
    const enumSchema: JsonSchemaProperty = {
      title: "User Preferences",
      description: "Configuration with enum values",
      type: "object",
      properties: {
        theme: {
          title: "Theme",
          description: "Color theme preference",
          type: "string",
          enum: ["light", "dark", "auto"],
        },
        size: {
          title: "Size",
          description: "UI size preference",
          type: "string",
          enum: ["small", "medium", "large"],
        },
        notifications: {
          title: "Notifications",
          description: "Notification level",
          type: "integer",
          enum: [0, 1, 2, 3],
        },
      },
      required: ["theme"],
      additionalProperties: false,
    }

    const model = model_from_schema(enumSchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(enumSchema)
  })

  it("preserves an object with a required array through round-trip conversion", () => {
    const objectWithRequiredArraySchema: JsonSchemaProperty = {
      type: "object",
      properties: {
        username: {
          title: "Username",
          description: "User's username",
          type: "string",
        },
        roles: {
          title: "Roles",
          description: "User's assigned roles",
          type: "array",
          items: {
            title: "Role",
            description: "A role name",
            type: "string",
          },
        },
        permissions: {
          title: "Permissions",
          description: "User's permissions",
          type: "array",
          items: {
            title: "Permission",
            description: "Permission object",
            type: "object",
            properties: {
              resource: {
                title: "Resource",
                description: "Resource name",
                type: "string",
              },
              actions: {
                title: "Actions",
                description: "Allowed actions",
                type: "array",
                items: {
                  title: "Action",
                  description: "An action name",
                  type: "string",
                },
              },
            },
            required: ["resource", "actions"],
            additionalProperties: false,
          },
        },
      },
      required: ["username", "roles", "permissions"],
      additionalProperties: false,
    }

    const model = model_from_schema(objectWithRequiredArraySchema)
    const reconstructedSchema = schema_from_model(model, false)

    expect(reconstructedSchema).toEqual(objectWithRequiredArraySchema)
  })
})

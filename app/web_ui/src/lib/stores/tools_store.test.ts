import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { tool_id_to_function_name } from "./tools_store"
import { client } from "$lib/api_client"

// Mock the API client
vi.mock("$lib/api_client", () => ({
  client: {
    GET: vi.fn(),
  },
}))

describe("tools_store", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe("tool_id_to_function_name", () => {
    it("should return function name for valid tool ID", async () => {
      const mockResponse = {
        data: {
          tool_id: "test_tool_id",
          function_name: "test_function_name",
          description: "Test tool description",
          parameters: {
            type: "object",
            properties: {
              input: {
                type: "string",
                description: "Input parameter",
              },
            },
            required: ["input"],
          },
          definition: {
            function: {
              name: "test_function_name",
              description: "Test tool description",
              parameters: {
                type: "object",
                properties: {
                  input: {
                    type: "string",
                    description: "Input parameter",
                  },
                },
                required: ["input"],
              },
            },
          },
        },
        error: undefined,
        response: new Response(),
      }

      vi.mocked(client.GET).mockResolvedValue(mockResponse)

      const result = await tool_id_to_function_name(
        "test_tool_id",
        "test_project_id",
        "test_task_id",
      )

      expect(result).toBe("test_function_name")
      expect(client.GET).toHaveBeenCalledWith(
        "/api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition",
        {
          params: {
            path: {
              project_id: "test_project_id",
              task_id: "test_task_id",
              tool_id: "test_tool_id",
            },
          },
        },
      )
    })

    it("should throw error when API call fails", async () => {
      const mockError = {
        data: null,
        error: {
          status: 404,
          statusText: "Not Found",
          body: {
            detail: "Tool not found",
          },
        },
        response: new Response(),
      } as any

      vi.mocked(client.GET).mockResolvedValue(mockError)

      await expect(
        tool_id_to_function_name(
          "invalid_tool_id",
          "test_project_id",
          "test_task_id",
        ),
      ).rejects.toEqual(mockError.error)

      expect(client.GET).toHaveBeenCalledWith(
        "/api/projects/{project_id}/tasks/{task_id}/tools/{tool_id}/definition",
        {
          params: {
            path: {
              project_id: "test_project_id",
              task_id: "test_task_id",
              tool_id: "invalid_tool_id",
            },
          },
        },
      )
    })

    it("should handle network errors", async () => {
      const networkError = new Error("Network error")
      vi.mocked(client.GET).mockRejectedValue(networkError)

      await expect(
        tool_id_to_function_name(
          "test_tool_id",
          "test_project_id",
          "test_task_id",
        ),
      ).rejects.toThrow("Network error")
    })

    it("should handle missing function_name in response", async () => {
      const mockResponse = {
        data: {
          tool_id: "test_tool_id",
          function_name: null, // Missing function name
          description: "Test tool description",
          parameters: {},
          definition: {
            function: {
              name: "test_function_name",
              description: "Test tool description",
              parameters: {},
            },
          },
        },
        error: undefined,
        response: new Response(),
      }

      vi.mocked(client.GET).mockResolvedValue(mockResponse)

      const result = await tool_id_to_function_name(
        "test_tool_id",
        "test_project_id",
        "test_task_id",
      )

      expect(result).toBe(null)
    })

    it("should handle empty response data", async () => {
      const mockResponse = {
        data: null,
        error: undefined,
        response: new Response(),
      }

      vi.mocked(client.GET).mockResolvedValue(mockResponse)

      await expect(
        tool_id_to_function_name(
          "test_tool_id",
          "test_project_id",
          "test_task_id",
        ),
      ).rejects.toThrow()
    })
  })
})

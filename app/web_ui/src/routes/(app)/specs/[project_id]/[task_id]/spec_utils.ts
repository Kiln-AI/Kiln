import { client } from "$lib/api_client"
import type { Spec, SpecStatus, SpecType } from "$lib/types"
import { spec_field_configs } from "./select_template/spec_templates"

/**
 * Build a definition string from properties
 * @param specType - The type of spec
 * @param properties - The properties of the spec
 * @returns The definition string
 */
export function buildSpecDefinition(
  specType: SpecType,
  properties: Record<string, string | null>,
): string {
  const fieldConfigs = spec_field_configs[specType]
  const parts: string[] = []

  for (const field of fieldConfigs) {
    const value = properties[field.key]
    if (value && value.trim()) {
      parts.push(`## ${field.label}\n${value}`)
    }
  }

  return parts.join("\n\n")
}

/**
 * Check if Kiln Copilot is connected (has API key configured)
 * @returns true if copilot is available, false otherwise
 * @throws Error if the settings API call fails
 */
export async function checkKilnCopilotAvailable(): Promise<boolean> {
  const { data, error } = await client.GET("/api/settings")
  if (error) {
    throw error
  }
  if (!data) {
    throw new Error("Failed to load Kiln settings")
  }
  return !!data["kiln_copilot_api_key"]
}

/**
 * Update a spec's priority via the API
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param spec - The spec to update
 * @param newPriority - The new priority value
 * @returns The updated spec
 * @throws Error if the API call fails
 */
export async function updateSpecPriority(
  project_id: string,
  task_id: string,
  spec: Spec,
  newPriority: number,
): Promise<Spec> {
  if (!spec.id) {
    throw new Error("Spec ID is required")
  }

  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
    {
      params: {
        path: { project_id, task_id, spec_id: spec.id },
      },
      body: {
        priority: newPriority as 0 | 1 | 2 | 3,
      },
    },
  )

  if (error) {
    throw error
  }

  return data
}

/**
 * Update a spec's status via the API
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param spec - The spec to update
 * @param newStatus - The new status value
 * @returns The updated spec
 * @throws Error if the API call fails
 */
export async function updateSpecStatus(
  project_id: string,
  task_id: string,
  spec: Spec,
  newStatus: SpecStatus,
): Promise<Spec> {
  if (!spec.id) {
    throw new Error("Spec ID is required")
  }

  const { data, error } = await client.PATCH(
    "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
    {
      params: {
        path: { project_id, task_id, spec_id: spec.id },
      },
      body: {
        status: newStatus,
      },
    },
  )

  if (error) {
    throw error
  }

  return data
}

/**
 * Extract a tag from a filter_id string (e.g., "tag::my_tag" -> "my_tag")
 * @param filter_id - The filter ID to extract the tag from
 * @returns The tag if the filter_id is a tag filter, undefined otherwise
 */
export function tagFromFilterId(filter_id: string): string | undefined {
  if (filter_id.startsWith("tag::")) {
    return filter_id.replace("tag::", "")
  }
  return undefined
}

/**
 * Generate a dataset link from a filter_id
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param filter_id - The filter ID to generate a link from
 * @returns The dataset URL if the filter_id is a tag filter, undefined otherwise
 */
export function linkFromFilterId(
  project_id: string,
  task_id: string,
  filter_id: string | null | undefined,
): string | undefined {
  if (!filter_id) {
    return undefined
  }
  const tag = tagFromFilterId(filter_id)
  if (tag) {
    return `/dataset/${project_id}/${task_id}?tags=${tag}`
  }
  return undefined
}

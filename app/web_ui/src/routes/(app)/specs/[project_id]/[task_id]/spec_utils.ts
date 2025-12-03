import { client } from "$lib/api_client"
import { goto } from "$app/navigation"
import type { SpecProperties, SpecType } from "$lib/types"
import { buildDefinitionFromProperties } from "./select_template/spec_templates"

/**
 * Navigate to review_spec page after storing form data
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param name - The spec name
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 */
export async function navigateToReviewSpec(
  project_id: string,
  task_id: string,
  name: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
): Promise<void> {
  // Store form data in sessionStorage to pass to review page
  const formData = {
    name,
    spec_type,
    property_values,
  }
  sessionStorage.setItem(
    `spec_refine_${project_id}_${task_id}`,
    JSON.stringify(formData),
  )

  // Navigate to review_spec page
  goto(`/specs/${project_id}/${task_id}/review_spec`)
}

/**
 * Create a new spec via the API
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param name - The spec name
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 * @returns The created spec ID or null if creation failed
 * @throws Error if the API call fails
 */
export async function createSpec(
  project_id: string,
  task_id: string,
  name: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
): Promise<string | null> {
  // Build the properties object with spec_type
  const properties = {
    spec_type: spec_type,
    ...property_values,
  } as SpecProperties

  // Build definition from properties
  const definition = buildDefinitionFromProperties(spec_type, property_values)

  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/spec",
    {
      params: {
        path: { project_id, task_id },
      },
      body: {
        name,
        definition,
        properties,
        priority: 1,
        status: "active",
        tags: [],
        eval_id: null,
      },
    },
  )

  if (error) {
    throw error
  }

  // Clear the sessionStorage after successful creation
  if (data?.id) {
    const formDataKey = `spec_refine_${project_id}_${task_id}`
    sessionStorage.removeItem(formDataKey)
  }

  return data?.id || null
}

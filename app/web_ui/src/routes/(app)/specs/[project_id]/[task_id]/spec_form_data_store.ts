import type { SpecType } from "$lib/types"

export type SpecFormData = {
  name: string
  spec_type: SpecType
  property_values: Record<string, string | null>
  evaluate_full_trace: boolean
}

/**
 * Type guard to validate if unknown data matches SpecFormData structure
 */
function isSpecFormData(data: unknown): data is SpecFormData {
  if (!data || typeof data !== "object") return false
  const d = data as Record<string, unknown>

  return (
    typeof d.name === "string" &&
    typeof d.spec_type === "string" &&
    typeof d.property_values === "object" &&
    d.property_values !== null &&
    typeof d.evaluate_full_trace === "boolean"
  )
}

/**
 * Safely parse SpecFormData from sessionStorage
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @returns The parsed form data or null if not found or invalid
 */
export function loadSpecFormData(
  project_id: string,
  task_id: string,
): SpecFormData | null {
  try {
    const formDataKey = `spec_refine_${project_id}_${task_id}`
    const storedData = sessionStorage.getItem(formDataKey)

    if (!storedData) {
      return null
    }

    const parsed = JSON.parse(storedData)

    if (!isSpecFormData(parsed)) {
      console.error("Invalid SpecFormData format in sessionStorage")
      return null
    }

    return parsed
  } catch (error) {
    console.error("Failed to parse SpecFormData from sessionStorage:", error)
    return null
  }
}

/**
 * Save SpecFormData to sessionStorage
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param formData - The form data to save
 */
export function saveSpecFormData(
  project_id: string,
  task_id: string,
  formData: SpecFormData,
): void {
  const formDataKey = `spec_refine_${project_id}_${task_id}`
  sessionStorage.setItem(formDataKey, JSON.stringify(formData))
}

/**
 * Clear SpecFormData from sessionStorage
 * @param project_id - The project ID
 * @param task_id - The task ID
 */
export function clearSpecFormData(project_id: string, task_id: string): void {
  const formDataKey = `spec_refine_${project_id}_${task_id}`
  sessionStorage.removeItem(formDataKey)
}

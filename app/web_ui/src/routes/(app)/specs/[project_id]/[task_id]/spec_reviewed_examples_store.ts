import { client } from "$lib/api_client"

/**
 * A reviewed example from the spec review process.
 * These examples form the golden dataset for the spec's eval.
 */
export type ReviewedExample = {
  input: string
  output: string
  user_says_meets_spec: boolean
  feedback: string | null
  model_says_meets_spec: boolean
}

/**
 * Get the sessionStorage key for reviewed examples.
 */
function getStorageKey(project_id: string, task_id: string): string {
  return `spec_reviewed_examples_${project_id}_${task_id}`
}

/**
 * Store reviewed examples in sessionStorage.
 * If examples already exist, unions them together (useful for multiple review cycles).
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param examples - The reviewed examples to store
 */
export function storeReviewedExamples(
  project_id: string,
  task_id: string,
  examples: ReviewedExample[],
): void {
  const key = getStorageKey(project_id, task_id)
  const existingData = sessionStorage.getItem(key)

  let allExamples: ReviewedExample[] = []
  if (existingData) {
    try {
      allExamples = JSON.parse(existingData) as ReviewedExample[]
    } catch {
      console.error("Error parsing existing reviewed examples", existingData)
      allExamples = []
    }
  }

  // Union the new examples with existing ones
  allExamples = [...allExamples, ...examples]
  sessionStorage.setItem(key, JSON.stringify(allExamples))
}

/**
 * Get all accumulated reviewed examples from sessionStorage.
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @returns The accumulated reviewed examples, or empty array if none
 */
export function getStoredReviewedExamples(
  project_id: string,
  task_id: string,
): ReviewedExample[] {
  const key = getStorageKey(project_id, task_id)
  const data = sessionStorage.getItem(key)
  if (!data) return []

  try {
    return JSON.parse(data) as ReviewedExample[]
  } catch {
    console.error("Error parsing stored reviewed examples", data)
    return []
  }
}

/**
 * Clear stored reviewed examples from sessionStorage.
 * @param project_id - The project ID
 * @param task_id - The task ID
 */
export function clearStoredReviewedExamples(
  project_id: string,
  task_id: string,
): void {
  const key = getStorageKey(project_id, task_id)
  sessionStorage.removeItem(key)
}

/**
 * Save reviewed examples as golden dataset by creating new TaskRuns
 * with the golden tag and human ratings.
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param examples - The reviewed examples (input/output with meets_spec rating)
 * @param goldenTag - The tag to apply to mark these as golden dataset items
 * @param evalScoreName - The name of the eval output score (typically the spec_type)
 */
export async function saveReviewedExamplesAsGoldenDataset(
  project_id: string,
  task_id: string,
  examples: ReviewedExample[],
  goldenTag: string,
  evalScoreName: string,
): Promise<void> {
  // Create a TaskRun for each reviewed example with the golden tag
  // The human rating is stored in requirement_ratings with key "named::<evalScoreName>"
  // to match the eval's output score
  for (const example of examples) {
    const ratingKey = `named::${evalScoreName}`
    const { error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/runs",
      {
        params: {
          path: { project_id, task_id },
        },
        body: {
          input: example.input,
          output: example.output,
          tags: [goldenTag],
          rating: {
            v: 1,
            type: "five_star",
            requirement_ratings: {
              [ratingKey]: {
                type: "pass_fail",
                value: example.user_says_meets_spec ? 1.0 : 0.0,
              },
            },
          },
          model_name: "kiln-copilot",
          model_provider: "kiln",
          adapter_name: "kiln-adapter",
        },
      },
    )

    if (error) {
      throw error
    }
  }
}

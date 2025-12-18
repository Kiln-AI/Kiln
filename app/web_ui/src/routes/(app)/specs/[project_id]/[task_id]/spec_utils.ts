import { client } from "$lib/api_client"
import { goto } from "$app/navigation"
import type {
  EvalDataType,
  EvalOutputScore,
  EvalTemplateId,
  Spec,
  SpecProperties,
  SpecStatus,
  SpecType,
} from "$lib/types"
import { buildDefinitionFromProperties } from "./select_template/spec_templates"
import {
  type ReviewedExample,
  clearStoredReviewedExamples,
  getStoredReviewedExamples,
  saveReviewedExamplesAsGoldenDataset,
} from "./spec_reviewed_examples_store"
import {
  type SpecFormData,
  loadSpecFormData,
  saveSpecFormData,
  clearSpecFormData,
} from "./spec_form_data_store"

// Re-export for convenience
export type { ReviewedExample, SpecFormData }
export { storeReviewedExamples } from "./spec_reviewed_examples_store"
export { loadSpecFormData, saveSpecFormData, clearSpecFormData }

/**
 * Navigate to review_spec page after storing form data
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param name - The spec name
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 * @param evaluate_full_trace - Whether to evaluate full trace vs final answer
 */
export async function navigateToReviewSpec(
  project_id: string,
  task_id: string,
  name: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  evaluate_full_trace: boolean = false,
): Promise<void> {
  // Store form data in sessionStorage to pass to review page
  const formData: SpecFormData = {
    name,
    spec_type,
    property_values,
    evaluate_full_trace,
  }
  saveSpecFormData(project_id, task_id, formData)

  // Navigate to review_spec page
  goto(`/specs/${project_id}/${task_id}/review_spec`)
}

/**
 * Create a new spec via the API.
 * Also creates a new eval for the spec and saves any accumulated reviewed examples as the golden dataset.
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param name - The spec name
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 * @param evaluate_full_trace - Whether to evaluate full trace vs final answer
 * @returns The created spec ID
 * @throws Error if the API call fails
 */
export async function createSpec(
  project_id: string,
  task_id: string,
  name: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  evaluate_full_trace: boolean = false,
): Promise<string> {
  // First create a new eval for the spec under the hood

  const eval_id = await createEval(
    project_id,
    task_id,
    name,
    spec_type,
    evaluate_full_trace,
  )

  // Save any accumulated reviewed examples as the golden dataset
  const reviewed_examples = getStoredReviewedExamples(project_id, task_id)
  if (reviewed_examples.length > 0) {
    const goldenTag = specEvalTag(name) + "_golden"
    await saveReviewedExamplesAsGoldenDataset(
      project_id,
      task_id,
      reviewed_examples,
      goldenTag,
      spec_type, // The eval output score name matches the spec_type
    )
  }

  // Build the properties object with spec_type, filtering out null values
  const filteredPropertyValues = Object.fromEntries(
    Object.entries(property_values).filter(([_, value]) => value !== null),
  )
  const properties = {
    spec_type: spec_type,
    ...filteredPropertyValues,
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
        eval_id: eval_id,
      },
    },
  )

  if (error) {
    throw error
  }

  if (!data.id) {
    throw new Error("Failed to create spec")
  }

  // Clear the sessionStorage after successful creation
  clearSpecFormData(project_id, task_id)
  // Also clear the reviewed examples storage
  clearStoredReviewedExamples(project_id, task_id)

  return data.id
}

async function createEval(
  project_id: string,
  task_id: string,
  spec_name: string,
  spec_type: SpecType,
  evaluate_full_trace: boolean = false,
): Promise<string> {
  const name = spec_name
  const description = `An eval to measure if the model's behaviour meets the spec: ${spec_name}.`
  const template = specEvalTemplate(spec_type)
  const output_scores = [specEvalOutputScore(spec_type)]
  const tag = specEvalTag(spec_name)
  const eval_set_filter_id = `tag::${tag}`
  const eval_configs_filter_id = `tag::${tag}_golden`
  const evaluation_data_type = specEvalDataType(spec_type, evaluate_full_trace)
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/create_evaluator",
    {
      params: {
        path: { project_id, task_id },
      },
      body: {
        name,
        description,
        template,
        output_scores,
        eval_set_filter_id,
        eval_configs_filter_id,
        template_properties: null,
        evaluation_data_type,
      },
    },
  )
  if (error) {
    throw error
  }

  if (!data.id) {
    throw new Error("Failed to create eval for spec")
  }

  return data.id
}

function specEvalOutputScore(spec_type: SpecType): EvalOutputScore {
  return {
    name: spec_type,
    type: "pass_fail",
    instruction: "Evaluate if the model's behaviour meets the spec.",
  }
}

function specEvalDataType(
  spec_type: SpecType,
  evaluate_full_trace: boolean = false,
): EvalDataType {
  if (spec_type === "reference_answer_accuracy") {
    return "reference_answer"
  }

  if (evaluate_full_trace) {
    return "full_trace"
  } else {
    return "final_answer"
  }
}

function specEvalTemplate(spec_type: SpecType): EvalTemplateId | null {
  switch (spec_type) {
    case "appropriate_tool_use":
      return "tool_call"
    case "reference_answer_accuracy":
      return "rag"
    case "factual_correctness":
      return "factual_correctness"
    case "toxicity":
      return "toxicity"
    case "bias":
      return "bias"
    case "maliciousness":
      return "maliciousness"
    case "jailbreak":
      return "jailbreak"
    case "issue":
      return "kiln_issue"
    case "desired_behaviour":
      return "desired_behaviour"
    case "tone":
    case "formatting":
    case "localization":
    case "hallucinations":
    case "completeness":
    case "nsfw":
    case "taboo":
    case "prompt_leakage":
      return null
    default: {
      const _exhaustive: never = spec_type
      void _exhaustive
      return null
    }
  }
}

function specEvalTag(spec_name: string): string {
  const tag = spec_name.toLowerCase().replace(/ /g, "_")
  if (tag.length === 0) {
    return "eval_" + (Math.floor(Math.random() * (99999 - 10000 + 1)) + 10000)
  }
  if (tag.length > 32) {
    return tag.slice(0, 32)
  }
  return tag
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
        name: spec.name,
        definition: spec.definition,
        properties: spec.properties,
        priority: newPriority as 0 | 1 | 2 | 3,
        status: spec.status,
        tags: spec.tags,
        eval_id: spec.eval_id ?? null,
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
        name: spec.name,
        definition: spec.definition,
        properties: spec.properties,
        priority: spec.priority,
        status: newStatus,
        tags: spec.tags,
        eval_id: spec.eval_id ?? null,
      },
    },
  )

  if (error) {
    throw error
  }

  return data
}

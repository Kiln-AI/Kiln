import { client } from "$lib/api_client"
import { goto } from "$app/navigation"
import type {
  EvalDataType,
  EvalOutputScore,
  EvalTemplateId,
  SpecProperties,
  SpecType,
  TaskRun,
} from "$lib/types"
import { buildDefinitionFromProperties as buildDefinition } from "./select_template/spec_templates"
import { createKilnError } from "$lib/utils/error_handlers"
import { load_task } from "$lib/stores"

// Re-export for convenience
export { buildDefinition as buildDefinitionFromProperties }

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
  // First create a new eval for the spec under the hood
  const eval_id = await createEval(project_id, task_id, name, spec_type)
  if (!eval_id) {
    throw createKilnError("Failed to create eval for spec")
  }

  // Generate eval data batch before creating the spec
  const tag = specEvalTag(name)
  await generateAndSaveEvalData(
    project_id,
    task_id,
    spec_type,
    property_values,
    tag,
  )

  // Build the properties object with spec_type, filtering out null values
  const filteredPropertyValues = Object.fromEntries(
    Object.entries(property_values).filter(([_, value]) => value !== null),
  )
  const properties = {
    spec_type: spec_type,
    ...filteredPropertyValues,
  } as SpecProperties

  // Build definition from properties
  const definition = buildDefinition(spec_type, property_values)

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

  // Clear the sessionStorage after successful creation
  if (data?.id) {
    const formDataKey = `spec_refine_${project_id}_${task_id}`
    sessionStorage.removeItem(formDataKey)
  }

  return data?.id || null
}

async function createEval(
  project_id: string,
  task_id: string,
  spec_name: string,
  spec_type: SpecType,
): Promise<string | null> {
  const name = spec_name
  const description = `An eval to measure if the model's behaviour meets the spec: ${spec_name}.`
  const template = specEvalTemplate(spec_type)
  const output_scores = [specEvalOutputScore(spec_type)]
  const tag = specEvalTag(spec_name)
  const eval_set_filter_id = `tag::${tag}`
  const eval_configs_filter_id = `tag::${tag}_golden`
  const evaluation_data_type = specEvalDataType(spec_type)
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
  return data?.id || null
}

function specEvalOutputScore(spec_type: SpecType): EvalOutputScore {
  return {
    name: spec_type,
    type: "pass_fail",
    instruction: "Evaluate if the model's behaviour meets the spec.",
  }
}

function specEvalDataType(spec_type: SpecType): EvalDataType {
  if (spec_type === "appropriate_tool_use") {
    return "full_trace"
  }
  if (spec_type === "reference_answer_accuracy") {
    return "reference_answer"
  }
  return "final_answer"
}

function specEvalTemplate(spec_type: SpecType): EvalTemplateId | null {
  if (spec_type === "appropriate_tool_use") {
    return "tool_call"
  }
  if (spec_type === "reference_answer_accuracy") {
    return "rag"
  }
  if (spec_type === "desired_behaviour") {
    return "desired_behaviour"
  }
  if (spec_type === "issue") {
    return "kiln_issue"
  }
  if (spec_type === "factual_correctness") {
    return "factual_correctness"
  }
  if (spec_type === "toxicity") {
    return "toxicity"
  }
  if (spec_type === "bias") {
    return "bias"
  }
  if (spec_type === "maliciousness") {
    return "maliciousness"
  }
  if (spec_type === "jailbreak") {
    return "jailbreak"
  }
  return null
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
 * Generate eval data using the generate_batch API and save as TaskRuns
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 * @param tag - The eval tag to apply to generated runs
 */
async function generateAndSaveEvalData(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  tag: string,
): Promise<void> {
  // Load the task to get instruction and schemas
  const task = await load_task(project_id, task_id)
  if (!task) {
    throw createKilnError("Failed to load task")
  }

  // Build the spec rendered prompt template from property values
  const spec_definition = buildDefinition(spec_type, property_values)

  // Call the generate_batch API
  const { data, error } = await client.POST("/api/spec/generate_batch", {
    body: {
      task_prompt_with_few_shot: task.instruction || "",
      task_input_schema: task.input_json_schema
        ? JSON.stringify(task.input_json_schema)
        : "",
      task_output_schema: task.output_json_schema
        ? JSON.stringify(task.output_json_schema)
        : "",
      spec_rendered_prompt_template: spec_definition,
      num_samples_per_topic: 10,
      num_topics: 10,
      enable_scoring: false,
    },
  })

  if (error || !data) {
    throw createKilnError(error || "Failed to generate batch")
  }

  // Convert examples to TaskRuns and save them
  type ExampleForFeedback = {
    input: string
    output: string
    exhibits_issue: boolean
  }
  const examples = (data as { examples_for_feedback: ExampleForFeedback[] })
    .examples_for_feedback

  // Save each example as a TaskRun with the eval tag
  for (const example of examples) {
    const taskRun: TaskRun = {
      v: 1,
      id: generate_id(),
      path: null,
      created_at: new Date().toISOString(),
      input: example.input,
      output: {
        v: 1,
        output: example.output,
        source: {
          type: "synthetic",
          properties: {
            adapter_name: "spec_eval_data_gen",
            model_name: "spec_eval_data_gen",
            model_provider: "kiln",
          },
        },
      },
      input_source: {
        type: "synthetic",
        properties: {
          adapter_name: "spec_eval_data_gen",
          model_name: "spec_eval_data_gen",
          model_provider: "kiln",
        },
      },
      tags: [tag],
    }

    // Save the run
    const { error: saveError } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/save_sample",
      {
        params: {
          path: { project_id, task_id },
        },
        body: taskRun,
      },
    )

    if (saveError) {
      // Log error but continue saving other runs
      console.error("Failed to save run:", saveError)
    }
  }
}

function generate_id(): string {
  // Generate a 12 digit random integer string, matching Python's generate_model_id()
  // which does: str(uuid.uuid4().int)[:12]
  const randomInt = Math.floor(Math.random() * 1000000000000)
  return randomInt.toString().padStart(12, "0")
}

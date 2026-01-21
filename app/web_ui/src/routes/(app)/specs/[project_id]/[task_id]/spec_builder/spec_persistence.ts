import { client } from "$lib/api_client"
import type {
  EvalDataType,
  EvalOutputScore,
  EvalTemplateId,
  ModelProviderName,
  SpecProperties,
  SpecType,
  TaskRun,
} from "$lib/types"
import { buildSpecDefinition } from "../spec_utils"
import { load_task } from "$lib/stores"

/**
 * A reviewed example from the spec review process.
 * These examples form the golden dataset for the spec's eval.
 * When used as a ReviewRow (with id), user_says_meets_spec may be undefined if not yet reviewed.
 */
export type ReviewedExample = {
  input: string
  output: string
  model_says_meets_spec: boolean
  user_says_meets_spec?: boolean
  feedback: string
}

export type JudgeInfo = {
  prompt: string
  model_id: string
  model_provider: ModelProviderName
}

/**
 * Create a new spec via the API.
 * Also creates a new eval for the spec and saves any provided reviewed examples as the golden dataset.
 * @param project_id - The project ID
 * @param task_id - The task ID
 * @param name - The spec name
 * @param spec_type - The spec type
 * @param property_values - The property values for the spec
 * @param use_kiln_copilot - Whether to use kiln copilot features
 * @param evaluate_full_trace - Whether to evaluate full trace vs final answer
 * @param reviewed_examples - Optional array of reviewed examples to save as golden dataset
 * @returns The created spec ID
 * @throws Error if the API call fails
 */
export async function createSpec(
  project_id: string,
  task_id: string,
  task_description: string,
  name: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  use_kiln_copilot: boolean,
  evaluate_full_trace: boolean = false,
  reviewed_examples: ReviewedExample[] = [],
  judge_info: JudgeInfo | null = null,
  signal?: AbortSignal,
): Promise<string> {
  // First create a new eval for the spec under the hood
  const eval_id = await createEval(
    project_id,
    task_id,
    name,
    spec_type,
    evaluate_full_trace,
  )

  try {
    if (use_kiln_copilot) {
      if (judge_info) {
        await createJudgeAndSetAsDefault(
          project_id,
          task_id,
          task_description,
          eval_id,
          judge_info,
        )
      }

      // Generate eval data set
      const evalTag = "eval_" + snakeCase(name)
      await generateAndSaveEvalData(
        project_id,
        task_id,
        spec_type,
        property_values,
        evalTag,
        signal,
      )

      // Save any provided reviewed examples as the golden dataset
      if (reviewed_examples.length > 0) {
        const goldenTag = "eval_golden_" + snakeCase(name)
        await saveReviewedExamplesAsGoldenDataset(
          project_id,
          task_id,
          reviewed_examples,
          goldenTag,
          name,
        )
      }
    }

    // Build the properties object with spec_type, filtering out null and empty values
    const filteredPropertyValues = Object.fromEntries(
      Object.entries(property_values).filter(
        ([_, value]) => value !== null && value.trim() !== "",
      ),
    )
    const properties = {
      spec_type: spec_type,
      ...filteredPropertyValues,
    } as SpecProperties

    // Build definition from properties
    const definition = buildSpecDefinition(spec_type, property_values)

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

    const spec_id = data.id
    if (!spec_id) {
      throw new Error("Failed to create spec")
    }
    return spec_id
  } catch (error) {
    // TODO: Cleanup the other data we created too?
    await cleanupEval(project_id, task_id, eval_id)
    throw error
  }
}

async function createJudgeAndSetAsDefault(
  project_id: string,
  task_id: string,
  task_description: string,
  eval_id: string,
  judge_info: JudgeInfo,
): Promise<void> {
  if (judge_info) {
    // Create a new eval config for the judge
    const { data: evalConfigData, error: evalConfigError } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/create_eval_config",
      {
        params: {
          path: {
            project_id,
            task_id,
            eval_id,
          },
        },
        body: {
          type: "llm_as_judge",
          model_name: judge_info.model_id,
          provider: judge_info.model_provider,
          properties: {
            eval_steps: [judge_info.prompt],
            task_description: task_description,
          },
        },
      },
    )

    if (evalConfigError) {
      throw evalConfigError
    }

    const eval_config_id = evalConfigData.id
    if (!eval_config_id) {
      throw new Error("Failed to create eval config for judge")
    }

    // Set the eval config as the default for the eval
    const { data: setDefaultData, error: setDefaultError } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/set_current_eval_config/{eval_config_id}",
      {
        params: {
          path: {
            project_id,
            task_id,
            eval_id,
            eval_config_id,
          },
        },
      },
    )

    if (setDefaultError) {
      throw setDefaultError
    }

    if (!setDefaultData) {
      throw new Error("Failed to set eval config as default")
    }
  }
}

async function createEval(
  project_id: string,
  task_id: string,
  spec_name: string,
  spec_type: SpecType,
  evaluate_full_trace: boolean = false,
): Promise<string> {
  const name = spec_name
  const template = specEvalTemplate(spec_type)
  const output_scores = [specEvalOutputScore(spec_name)]
  const snake_case_name = snakeCase(spec_name)
  const eval_set_filter_id = `tag::eval_${snake_case_name}`
  const eval_configs_filter_id = `tag::eval_golden_${snake_case_name}`
  const evaluation_data_type = specEvalDataType(spec_type, evaluate_full_trace)
  const { data, error } = await client.POST(
    "/api/projects/{project_id}/tasks/{task_id}/create_evaluator",
    {
      params: {
        path: { project_id, task_id },
      },
      body: {
        name,
        description: null,
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

  const eval_id = data.id
  if (!eval_id) {
    throw new Error("Failed to create eval for spec")
  }

  return eval_id
}

/**
 * Generate eval data using the generate_batch API and save as TaskRuns
 */
async function generateAndSaveEvalData(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  tag: string,
  signal?: AbortSignal,
): Promise<void> {
  // Load the task to get instruction and schemas
  const task = await load_task(project_id, task_id)
  if (!task) {
    throw new Error("Failed to load task")
  }

  // Build the spec rendered prompt template from property values
  const spec_definition = buildSpecDefinition(spec_type, property_values)

  // Call the generate_batch API
  // TODO: Add few shot examples to the task prompt if able
  // TODO: Fix task input/output schemas?
  const { data, error } = await client.POST("/api/copilot/generate_batch", {
    body: {
      task_prompt_with_few_shot: task.instruction || "",
      task_input_schema: task.input_json_schema
        ? JSON.stringify(task.input_json_schema)
        : "",
      task_output_schema: task.output_json_schema
        ? JSON.stringify(task.output_json_schema)
        : "",
      spec_rendered_prompt_template: spec_definition,
      num_samples_per_topic: 5,
      num_topics: 4, // TODO: 10 topics, 10 samples per topic
    },
    signal,
  })

  if (error) {
    throw error
  }

  if (!data) {
    throw new Error("Failed to generate batch")
  }

  const examples = Object.values(data.data_by_topic).flat()

  // Split examples 50/50 - half for eval, half for training
  const midpoint = Math.ceil(examples.length / 2)
  const evalExamples = examples.slice(0, midpoint)
  const trainExamples = examples.slice(midpoint)

  // Create the training tag by replacing "eval_" prefix with "eval_train_"
  const trainTag = tag.replace(/^eval_/, "eval_train_")

  // Save each example as a TaskRun with the appropriate tag
  const allExamplesWithTags = [
    ...evalExamples.map((example) => ({ example, tag })),
    ...trainExamples.map((example) => ({ example, tag: trainTag })),
  ]

  for (const { example, tag: exampleTag } of allExamplesWithTags) {
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
            adapter_name: "kiln-adapter",
            model_name: "kiln-copilot",
            model_provider: "kiln",
          },
        },
      },
      input_source: {
        type: "synthetic",
        properties: {
          adapter_name: "kiln-adapter",
          model_name: "kiln-copilot",
          model_provider: "kiln",
        },
      },
      tags: [exampleTag],
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
      throw saveError
    }
  }
}

/**
 * Save reviewed examples as golden dataset by creating new TaskRuns
 * with the golden tag and human ratings.
 */
async function saveReviewedExamplesAsGoldenDataset(
  project_id: string,
  task_id: string,
  examples: ReviewedExample[],
  goldenTag: string,
  spec_name: string,
): Promise<void> {
  // Create a TaskRun for each reviewed example with the golden tag
  // The human rating is stored in requirement_ratings with key "named::<spec_name>" (using spec name for eval output score name)
  for (const example of examples) {
    const ratingKey = `named::${spec_name}`
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

function generate_id(): string {
  // Generate a 12 digit random integer string, matching Python's generate_model_id()
  // which does: str(uuid.uuid4().int)[:12]
  const randomInt = Math.floor(Math.random() * 1000000000000)
  return randomInt.toString().padStart(12, "0")
}

function specEvalOutputScore(spec_name: string): EvalOutputScore {
  return {
    name: spec_name,
    type: "pass_fail",
    instruction: `Evaluate if the model's behaviour meets the spec: ${spec_name}.`,
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

function snakeCase(spec_name: string): string {
  return spec_name.toLowerCase().replace(/ /g, "_")
}

async function cleanupEval(
  project_id: string,
  task_id: string,
  eval_id: string,
): Promise<void> {
  try {
    await client.DELETE(
      "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}",
      {
        params: {
          path: { project_id, task_id, eval_id },
        },
      },
    )
  } catch (cleanupError) {
    console.error(
      "Failed to cleanup eval after spec creation failure:",
      cleanupError,
    )
  }
}

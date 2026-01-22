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
  model_name: string
  model_provider: ModelProviderName
}

function evalTagSuffix(spec_name: string): string {
  return snakeCase(spec_name) + "_" + generate_id()
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
  const eval_tag_suffix = evalTagSuffix(name)
  const eval_id = await createEval(
    project_id,
    task_id,
    name,
    spec_type,
    evaluate_full_trace,
    eval_tag_suffix,
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

      // Generate all examples
      const evalDataBatch = await generateEvalDataBatch(
        project_id,
        task_id,
        spec_type,
        property_values,
        signal,
      )

      const evalTag = "eval_" + eval_tag_suffix
      const trainTag = "eval_train_" + eval_tag_suffix
      const goldenTag = "eval_golden_" + eval_tag_suffix

      // Randomly sample examples for each set, removing from pool to avoid overlap
      const evalExamples = sampleAndRemove(evalDataBatch, MIN_EVAL_EXAMPLES)
      await saveGeneratedExamples(project_id, task_id, evalExamples, evalTag)

      const trainExamples = sampleAndRemove(evalDataBatch, MIN_TRAIN_EXAMPLES)
      await saveGeneratedExamples(project_id, task_id, trainExamples, trainTag)

      // Persist unrated golden examples from remaining pool if needed
      const unratedGoldenExampleCount = Math.max(0, MIN_GOLDEN_EXAMPLES - reviewed_examples.length)
      if (unratedGoldenExampleCount > 0) {
        const unratedGoldenExamples = sampleAndRemove(evalDataBatch, unratedGoldenExampleCount)
        await saveGeneratedExamples(project_id, task_id, unratedGoldenExamples, goldenTag)
      }
      
      // Save reviewed golden examples with ratings
      await saveReviewedExamples(project_id, task_id, reviewed_examples, goldenTag, name)
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
          model_name: judge_info.model_name,
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
  evalTagSuffix: string,
): Promise<string> {
  const name = spec_name
  const template = specEvalTemplate(spec_type)
  const output_scores = [specEvalOutputScore(spec_name)]
  const eval_set_filter_id = `tag::eval_${evalTagSuffix}`
  const eval_configs_filter_id = `tag::eval_golden_${evalTagSuffix}`
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

type GeneratedExample = {
  input: string
  output: string
}

const NUM_SAMPLES_PER_TOPIC = 5 // TODO: Make this 15
const NUM_TOPICS = 10 // TODO: Make this 15
const MIN_EVAL_EXAMPLES = 20 // TODO: Make this 100
const MIN_TRAIN_EXAMPLES = 20 // TODO: Make this 100
const MIN_GOLDEN_EXAMPLES = 10 // TODO: Make this 25
const KILN_COPILOT_MODEL_NAME = "kiln-copilot"
const KILN_COPILOT_MODEL_PROVIDER = "kiln"
const KILN_ADAPTER_NAME = "kiln-adapter"

/**
 * Generate eval data using the generate_batch API.
 * Returns the generated examples.
 */
async function generateEvalDataBatch(
  project_id: string,
  task_id: string,
  spec_type: SpecType,
  property_values: Record<string, string | null>,
  signal?: AbortSignal,
): Promise<GeneratedExample[]> {
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
      num_samples_per_topic: NUM_SAMPLES_PER_TOPIC,
      num_topics: NUM_TOPICS,
    },
    signal,
  })

  if (error) {
    throw error
  }

  if (!data) {
    throw new Error("Failed to generate batch")
  }

  return Object.values(data.data_by_topic).flat()
}

/**
 * Save generated examples as TaskRuns with the given tag.
 */
async function saveGeneratedExamples(
  project_id: string,
  task_id: string,
  examples: GeneratedExample[],
  tag: string,
): Promise<void> {
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
            adapter_name: KILN_ADAPTER_NAME,
            model_name: KILN_COPILOT_MODEL_NAME,
            model_provider: KILN_COPILOT_MODEL_PROVIDER,
          },
        },
      },
      input_source: {
        type: "synthetic",
        properties: {
          adapter_name: KILN_ADAPTER_NAME,
          model_name: KILN_COPILOT_MODEL_NAME,
          model_provider: KILN_COPILOT_MODEL_PROVIDER,
        },
      },
      tags: [tag],
    }

    const { error } = await client.POST(
      "/api/projects/{project_id}/tasks/{task_id}/save_sample",
      {
        params: {
          path: { project_id, task_id },
        },
        body: taskRun,
      },
    )

    if (error) {
      throw error
    }
  }
}

/**
 * Save reviewed examples by creating new TaskRuns with human ratings.
 */
async function saveReviewedExamples(
  project_id: string,
  task_id: string,
  examples: ReviewedExample[],
  tag: string,
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
          tags: [tag],
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
          model_name: KILN_COPILOT_MODEL_NAME,
          model_provider: KILN_COPILOT_MODEL_PROVIDER,
          adapter_name: KILN_ADAPTER_NAME,
        },
      },
    )

    if (error) {
      throw error
    }
  }
}

/**
 * Randomly sample and remove n items from an array using Fisher-Yates shuffle.
 * Mutates the input array by removing the sampled elements.
 */
function sampleAndRemove<T>(array: T[], n: number): T[] {
  const sampled: T[] = []
  const count = Math.min(n, array.length)
  for (let i = 0; i < count; i++) {
    const randomIndex = Math.floor(Math.random() * array.length)
    sampled.push(array[randomIndex])
    array.splice(randomIndex, 1)
  }
  return sampled
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

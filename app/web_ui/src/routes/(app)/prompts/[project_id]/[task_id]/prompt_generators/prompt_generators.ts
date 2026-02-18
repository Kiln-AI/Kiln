export type PromptGeneratorTemplate = {
  generator_id: string | null
  name: string
  description: string
  requires_data: boolean
  requires_repairs: boolean
  chain_of_thought: boolean
  recommended?: boolean
}

export type PromptGeneratorCategory = {
  category: string
  templates: PromptGeneratorTemplate[]
}

export const prompt_generator_categories: PromptGeneratorCategory[] = [
  {
    category: "Automatic Optimization",
    templates: [
      {
        generator_id: "kiln_prompt_optimizer",
        name: "Kiln Optimized",
        description:
          "Our state-of-the-art automatic prompt optimizer. We use evals to pinpoint and fix failure modes—no manual prompting required.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: false,
        recommended: true,
      },
    ],
  },
  {
    category: "Prompt Generators",
    templates: [
      {
        generator_id: "few_shot_prompt_builder",
        name: "Few-Shot",
        description: "Includes up to 4 examples from your dataset.",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: false,
      },
      {
        generator_id: "multi_shot_prompt_builder",
        name: "Many-Shot",
        description: "Includes up to 25 examples from your dataset.",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: false,
      },
      {
        generator_id: "repairs_prompt_builder",
        name: "Repair Multi-Shot",
        description:
          "Includes examples of human repairs from your dataset to help the model avoid common errors.",
        requires_data: true,
        requires_repairs: true,
        chain_of_thought: false,
      },
      {
        generator_id: "simple_chain_of_thought_prompt_builder",
        name: "Chain of Thought",
        description:
          "Give the model time to 'think' before answering. Zero-shot with reasoning.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: true,
      },
      {
        generator_id: "few_shot_chain_of_thought_prompt_builder",
        name: "Chain of Thought + Few Shot",
        description: "Combines chain-of-thought and few-shot (4 examples).",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: true,
      },
      {
        generator_id: "multi_shot_chain_of_thought_prompt_builder",
        name: "Chain of Thought + Many Shot",
        description: "Combines chain-of-thought and many-shot (25 examples).",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: true,
      },
    ],
  },
  {
    category: "Manual",
    templates: [
      {
        generator_id: null,
        name: "Custom",
        description: "Write your own prompt.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: false,
      },
    ],
  },
]

export function getPromptType(
  prompt_id: string,
  generator_id?: string | null,
): string {
  if (prompt_id.startsWith("fine_tune_prompt::")) return "Fine-Tune"
  if (prompt_id.startsWith("task_run_config::")) return "Frozen"
  if (generator_id) {
    const generator = prompt_generator_categories
      .flatMap((c) => c.templates)
      .find((t) => t.generator_id === generator_id)
    if (generator) return generator.name
  }
  if (prompt_id.startsWith("id::")) return "Custom"
  return "Unknown"
}

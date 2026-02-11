export type PromptGeneratorTemplate = {
  generator_id: string | null
  name: string
  description: string
  requires_data: boolean
  requires_repairs: boolean
  chain_of_thought: boolean
}

export type PromptGeneratorCategory = {
  category: string
  templates: PromptGeneratorTemplate[]
}

export const prompt_generator_categories: PromptGeneratorCategory[] = [
  {
    category: "Automated Optimization",
    templates: [
      {
        generator_id: "kiln_prompt_optimizer",
        name: "Kiln Prompt Optimizer",
        description:
          "Run GEPA to automatically optimize your prompt with training data.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: false,
      },
    ],
  },
  {
    category: "Standard Prompts",
    templates: [
      {
        generator_id: null,
        name: "Custom",
        description: "Write your own prompt from scratch.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: false,
      },
      {
        generator_id: "simple_prompt_builder",
        name: "Basic (Zero Shot)",
        description: "Just the prompt, no examples.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: false,
      },
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
    ],
  },
  {
    category: "Chain of Thought",
    templates: [
      {
        generator_id: "simple_chain_of_thought_prompt_builder",
        name: "Chain of Thought",
        description:
          "Give the LLM time to 'think' before answering. Zero-shot with reasoning.",
        requires_data: false,
        requires_repairs: false,
        chain_of_thought: true,
      },
      {
        generator_id: "few_shot_chain_of_thought_prompt_builder",
        name: "Chain of Thought - Few Shot",
        description: "Combines CoT and few-shot with up to 4 examples.",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: true,
      },
      {
        generator_id: "multi_shot_chain_of_thought_prompt_builder",
        name: "Chain of Thought - Many Shot",
        description: "Combines CoT and many-shot with up to 25 examples.",
        requires_data: true,
        requires_repairs: false,
        chain_of_thought: true,
      },
    ],
  },
]

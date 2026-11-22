---
description: >-
  Prompt generators build prompts for you combing best practices and data from
  your dataset
online_url: https://docs.kiln.tech/docs/prompts/prompt-generators
---

# Prompt Generators

### Prompt Generator Inputs

When you create a Kiln task you specify several fields which are used when generating prompts:

* Instructions: The core of your prompt. Describe the task as you would in a standard LLM prompt.
* Thinking Instructions: This field allows you to specify a portion of the prompt, which is only used when you select a "chain of thought" prompt template. If omitted, the default is "Think step by step, explaining your reasoning.".

These can be edited in `Settings > Edit Task > Task Instructions` .

### Adding Content for Multi-Shot Prompts

Multi-shot prompting is when you provide several examples in the prompt, and has been shown to greatly improve output quality.

In order to use multi-shot prompting in Kiln, we need some correct example content to use. Kiln makes this easy! Simply run your task in the Run tab of the UI, and rate the output. As you collect more 4 and 5 star responses, the set of available content for multi-shot prompting increases.

Kiln will automatically select content for multi-shot prompts using your dataset, using the following priority:

* 5-star [repairs](references/docs/repairing-responses.md): where a human has given feedback, repaired the response, and rated the repair 5-stars
* 5-star responses
* 4-star response

Responses with a 3-star or worse rating are never used, unless they have been [repaired](references/docs/repairing-responses.md) to 5-stars.

### Prompt Generators

Once you've setup your task and added some example content, you'll have a number of prompt generators to choose from:

* **Basic (Zero Shot)**: a prompt template that will only use your task definition (instructions and requirements). This prompt is deterministic, and won't change unless you edit your task.
* **Few Shot**: a multi-shot prompt that will include the 4 best examples from your dataset, on top of the basic prompt.
* **Many Shot**: a multi-shot prompt that will include the 25 best examples from your dataset, on top of the basic prompt.
* **Repair Multi Shot**: a multi-shot prompt that will include the 25 best examples from your dataset, on top of the basic prompt. This [prompt will use repaired examples](references/docs/repairing-responses.md) to show 1) the generated content which had issues, 2) the human feedback about what was incorrect, 3) the corrected 5-star content. This gives the LLM examples of common errors to avoid.
* **Basic Chain of Thought**: a [chain of thought](references/docs/reasoning-and-chain-of-thought.md) prompt template that will only use your task definition (instructions, requirements, and thinking instructions). Kiln will return the response in 2 stages, 1) thinking stage, 2) response stage. Both are stored in the dataset, but typically only stage 2 is used in the app/product. For structured tasks, the final answer must conform to the schema, but the thinking stage is plain text. This prompt is deterministic, and won't change unless you edit your task.
* **Chain of Thought - Few Shot**: a prompt that applies both the few shot template (4 examples), and chain-of-thought thinking instructions.
* **Chain of Thought - Many Shot**: a prompt that applies both the many shot template (25 examples), and chain-of-thought thinking instructions.

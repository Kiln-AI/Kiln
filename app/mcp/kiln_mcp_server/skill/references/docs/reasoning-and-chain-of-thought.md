---
description: Improve your model's quality with inference time scaling
icon: brain
---

# Reasoning & Chain of Thought

<figure><img src="../.gitbook/assets/reasoning (1).png" alt=""><figcaption></figcaption></figure>

{% hint style="info" %}
Want to dive in and build a reasoning model? See our [Guide for Training A Reasoning Model](references/docs/fine-tuning/guide-train-a-reasoning-model.md)
{% endhint %}

Kiln has powerful support for reasoning models and chain of thought. These techniques can generate higher quality results, while also reducing costs and improving performance.

<details>

<summary>What are reasoning models and chain of thought?</summary>

Reasoning models and chain of thought (COT) are methods that give models time to "think" before giving a final answer. Their "thinking" takes the form of discussing the request and possible answers in a stream of generated tokens. These additional tokens allow for more complex reasoning, step-by-step thinking, and have been shown to improve the quality of results.

These approaches are also known as "inference time scaling," where models improve from spending more compute power at inference time — as opposed to improving by spending more compute at training time.

While similar in some ways, the methods have some differences:

* **Chain of thought** is a method that's been around for a few years, and simply involves asking the model to think before giving an answer. This can be as simple as appending "Think step by step" to your prompt or adding detailed instructions for what the model should "think" about before giving its final answer.
* **Reasoning/thinking models** like Deepseek R1 or OpenAI's O3 are a newer form of inference time compute, where the model itself was trained to develop powerful reasoning skills. These models are trained with reinforcement learning, where the model is rewarded for being correct and penalized when incorrect. This training system uses deep learning to help models develop reasoning skills across a range of domains.

While reasoning models are generally more powerful than chain of thought, it's often worth testing both approaches for your use case. Thinking models strive to reason about everything effectively, but a well-crafted chain of thought prompt from a human expert can often outperform them when developing use-case-specific models/APIs.

</details>

### How Kiln handles reasoning models and chain of thought

Kiln has native support for both these methods. This includes:

* [**Creating Reasoning Models**](references/docs/reasoning-and-chain-of-thought.md#building-your-own-reasoning-model-distillation)**:** You can fine-tune/distill reasoning models using Kiln. Models train on your Kiln dataset, using samples generated from reasoning models. This approach allows you to build small, fast, and high-quality thinking models, tuned to your use case.
* [**Data Model**](https://docs.kiln.tech/developers/kiln-datamodel)**:** Our data model stores thinking separately from final answers, allowing you to evaluate or train on them independently.
* [**Custom Message Flow**](references/docs/reasoning-and-chain-of-thought.md#custom-message-chat-flow)**:** When using chain-of-thought with models that don't support reasoning we make a chain of calls to the model to formally separate the thinking from the answer.
* [**Structured Data**](references/docs/structured-data-json.md): Our chat call flow allows for the final answer messages to use structured data tools (json\_schema, json\_object, tool-calls, etc.) without adding "thinking" fields to your data structures.
* [**Prompts**](references/docs/prompts.md)**:** Prompts are divided into the primary system message and a separate "thinking instruction."
* **Reasoning Parsers:** Kiln includes parsers that separate out "thinking" from answers for common thinking models.

### Using Reasoning or COT in Kiln for inference

Using reasoning models or COT in Kiln is easy! Simply do one of the following:

* Run a model with any "Chain of Thought" prompt selected, including a custom prompt with thinking instructions included.
* Run a reasoning model (e.g., Deepseek R1) with any prompt. If a Chain of Thought prompt is used, the thinking instructions will be passed along to the model in the system prompt. If a non-COT prompt is used, the reasoning model will still "think," but using its own reasoning guidance.

Once the run is complete, you'll see both a final answer and reasoning in the model output.

### Building your own reasoning model (distillation)

Kiln can fine-tune a thinking model using your dataset. Often called distillation, these models can learn the reasoning strategies for your use case from examples in your Kiln dataset. By fine-tuning a model, you can produce a model that's smaller, faster, cheaper, and better than the original model (for your use case).

* See our guide on fine-tuning reasoning models
* See our guide for [general fine-tuning](references/docs/fine-tuning/fine-tuning-guide.md) (non-reasoning models)

{% hint style="info" %}
Kiln uses supervised fine tuning to distill reasoning models.
{% endhint %}

### Performance & Cost

Reasoning and COT doesn't necessarily mean slower or more costly requests. Sometimes a smaller model with these methods can be faster, better, and cheaper than a larger model performing the same task. Fine-tuning can help further reduce costs and improve quality.

### Supported Reasoning Models

Currently we support Deepseek R1 and its official distillations. We expect to see many more open reasoning models emerge over the next few months. See the [model capability list in our docs](references/docs/models-and-ai-providers.md#included-models-recommended) for the latest .

{% hint style="info" %}
While you can call OpenAI's reasoning models (o1, o3) from Kiln, they behave like normal models. OpenAI hides the reasoning tokens from users, only returning the final answer.
{% endhint %}

### Custom Message Chat Flow

Here's the message call flow Kiln uses for each configuration:

#### Normal Call-Flow (non-reasoning model)

* \[System-Message]: System prompt
* \[User-Message]: User inputs
* \[Assistant-Message]: Final Answer, optionally structured data

#### Chain of Thought Call-Flow (non-reasoning model):

* \[System-Message]: System prompt
* \[User-Message]: User inputs
* \[User-Message]: Thinking instructions. User-provided if available, defaults to "Think step by step, explaining your reasoning."
* \[Assistant-Message]: COT reasoning tokens
* \[User-Message]: Kiln managed message: "Considering the above, return a final result."
* \[Assistant-Message]: Final Answer, optionally structured data

This flow is also used on fine-tunes you create with Kiln if the fine-tune was created with the "Final answer and intermediate reasoning" training strategy.

#### Reasoning Model Call-Flow:

* \[System-Message]: System prompt, optionally appending thinking instructions if the selected prompt includes them.
* \[User-Message]: User inputs
* \[Assistant-Message]: Final Answer and reasoning in one message, but will be parsed into separate reasoning and answer fields. Will parse structured data if the task has structured output.

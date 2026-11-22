---
description: Built a reasoning model, like o3 or R1, for your use case
---

# Train a Reasoning Model

Kiln is a platform that makes building task-specific AI models easy and fast. By creating a fine-tuned model targeted to your use case, you can produce a model that's higher quality, faster and cheaper than standard foundation models.

In this guide, we'll walk through how to build a reasoning model, like OpenAI o3 or Deepseek R1, for your specific use case. The whole process can be completed in as little as 30 minutes, and does not require coding.

Also see our docs on [how Kiln supports Reasoning and Chain of Thought](references/docs/reasoning-and-chain-of-thought.md).

## How to Train a Task Specific Reasoning Model

We already have a [detailed guide on fine-tuning models](references/docs/fine-tuning/fine-tuning-guide.md). This article covers the settings to use throughout that process to ensure the final model you produce is a reasoning model, and not just a standard fine-tune.

### Training Demo Video

{% embed url="https://vimeo.com/1067942685/f2fbe3e3de" %}
Video walkthrough of creating a custom reasoning LLM
{% endembed %}

### Ensure your training data includes "reasoning"

When developing your training data with our [synthetic data generation](references/docs/synthetic-data-generation.md) tool, be sure to use either a reasoning model or chain-of-thought prompting. Using either of these will ensure your dataset has reasoning data to learn from. See our [model list](references/docs/models-and-ai-providers.md#included-models-recommended) for which models have native reasoning support.

See below for [how to choose between reasoning and chain of thought](references/docs/fine-tuning/guide-train-a-reasoning-model.md#choosing-between-reasoning-and-chain-of-thought).

<figure><img src="../../.gitbook/assets/run method.png" alt="" width="375"><figcaption><p>Synthetic Data Run Options</p></figcaption></figure>

{% hint style="info" %}
If you're using multi-shot prompting, also ensure your prompt examples have appropriate reasoning data. Consider a [custom prompt](references/docs/prompts.md#custom-prompts-saved-prompts) with examples demonstrating ideal reasoning for your task.
{% endhint %}

### Create a training dataset filtered to samples with reasoning

When creating your fine-tuning dataset, be sure to filter it to samples with reasoning/thinking checking "Filter to Reasoning Samples" as shown here:

<figure><img src="../../.gitbook/assets/filter to reasoning.png" alt="" width="375"><figcaption><p>Filtering your training dataset</p></figcaption></figure>

### Choose the correct training strategy

To train your own reasoning model, you must select the `Thinking - Learn both thinking and final response` in the `Reasoning` dropdown of Step 3. This will include the reasoning data when fine-tuning.

<figure><img src="../../.gitbook/assets/Screenshot 2025-05-26 at 9.18.25 PM.png" alt="" width="375"><figcaption><p>Select this on the "Create Fine Tune" screen</p></figcaption></figure>

If you select `Disabled` the fine-tune will only learn from the final result, not the reasoning. This is still a valid approach and could produce a viable model for your task. However, it won't produce a model with learned reasoning skills.

### Call your fine-tuned model with the appropriate prompt

When you call any fine-tune, we always recommend calling it with the same prompt used in training.

<figure><img src="../../.gitbook/assets/Screenshot 2025-02-05 at 9.56.17 AM.png" alt="" width="341"><figcaption><p>Kiln's Inference UI Options</p></figcaption></figure>

If calling your model from custom code, follow the chat call flow described in our [reasoning docs](references/docs/reasoning-and-chain-of-thought.md#chain-of-thought-call-flow-non-reasoning-model), and use the prompts used to fine-tune the model which can be found by clicking the model in the "Fine Tune" tab of Kiln's UI.

{% hint style="info" %}
If you want to call a fine-tune with a shorter prompt for performance reasons, consider training it with that prompt — even if sample data was generated with a longer prompt. The results will typically be better than using a prompt the model didn't see at training time.

To do this select "Custom Prompt" when creating the fine-tune, and set your prompt there.
{% endhint %}

### Choosing between Reasoning and Chain of Thought

The fine-tuning approach described in this article is a general approach that trains for an intermediate "thinking" output. This can be used for both reasoning models and chain of thought.

{% hint style="info" %}
Read about [the difference between reasoning models and chain of thought](references/docs/reasoning-and-chain-of-thought.md#what-are-reasoning-models-and-chain-of-thought).
{% endhint %}

Both approaches can build great task specific models. Which to choose depends on your use case. It can be worth training and comparing several to find the best option for you.

* **Distill a Reasoning Model**: Reasoning models have learned reasoning skills across a range of domains. If large reasoning models like Deepseek R1 perform well on your task, but are too expensive or slow, it can be a good choice to fine-tune a smaller model from R1 outputs (this is called distilling a model). The smaller model will learn task-specific reasoning patterns from R1 samples, and be faster and cheaper to run.
* **Chain of thought with default prompt**: Sometimes a simple "think step by step" prompt is all you need for chain of thought to greatly improve your quality of output. If large models work great with a simple prompt but smaller models fail to produce the same quality, you can build a fine-tune with task-specific examples so the smaller model can distill the thinking patterns from the larger model.
* **Chain of thought with a custom thinking prompt**: When building a model for a specific task, it's very possible you or your team understand the nuance of the task better than a generalized model like Deepseek R1. If you can create a "thinking instructions" prompt that works well with large models like Sonnet or GPT-4o, you can use that to build a synthetic training set, create a fine-tune, and reproduce that quality on a much smaller and faster model.

In each case, you're building a model that will be focused on the use-case samples it is trained on. This can produce a model that's faster, cheaper and higher quality than the original model, within the domain of your task.

{% hint style="info" %}
For the example in the demo video, I actually found custom chain-of-thought on Sonnet 3.5 to produce better content than Deepseek R1. It's worth experimenting with different models and prompts to find the best pair suited for your task, before jumping to building a synthetic dataset.
{% endhint %}

### Improving quality with human curation and feedback

Human curation feedback can add the nuance that makes a truly great model/product. Kiln offers a number of tools to make this easy:

* Have a subject matter expert [rate the synthetic training set](references/docs/reviewing-and-rating.md), and filter your training data to only use high quality samples.
* Have subject matter experts [repair poorly rated outputs](references/docs/repairing-responses.md), giving the model important examples of places it likely would have failed without fine-tuning.
* Use human-led chain of thought prompts as described [here](references/docs/fine-tuning/guide-train-a-reasoning-model.md#choosing-between-reasoning-and-chain-of-thought), to generate [large synthetic data sets](references/docs/synthetic-data-generation.md) for fine-tuning.
* When you find a pattern of bugs, use [synthetic data generation with human guidance](references/docs/synthetic-data-generation.md) to create samples of correct input/output pairs. Add these to your training set to fix the behaviour the next time you train.
* Use Kiln's [collaboration system](references/docs/collaboration/) to allow anyone on your team to contribute to model quality with feedback, data generation and quality. Our UI is designed for anyone, and does not require command line or coding skills.

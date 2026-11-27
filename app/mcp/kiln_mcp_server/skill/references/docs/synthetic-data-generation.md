---
description: Generate synthetic data for fine-tuning or evaluation
icon: robot
online_url: https://docs.kiln.tech/docs/synthetic-data-generation
---

# Synthetic Data Generation

Anyone can create thousands of synthetic data samples in just a few minutes using our interactive UI.

### Use Cases

Synthetic data is helpful for many reasons:

* **Evals:** Generate data for custom evals of your task performance
* **Fine-tuning:** Generate fine-tuning datasets
* **Built-in Templates:** Use our built-in data-gen templates like 'Jailbreaking' or 'Bias' to check your system for common issues (curated evals)
* **Addressing Bugs / Issues:** generate targeted data to reproduce a bug/issue, which can be used for training a fix, evaluating a fix, and backtesting
* **Prompting:** Generate examples to be used for few-shot or multi-shot prompting

### Video Walkthrough

{% hint style="info" %}
Kiln's UI has been improved since this video was recorded. You may notice small differences in the UI, but the overall flows are the same.
{% endhint %}

{% embed url="https://vimeo.com/1088940292" %}
Synthetic Data Generation Walkthrough
{% endembed %}

### How It Works

#### Automatic Synthetic Data Gen Prompting

Kiln doesn't require you to write complex custom synthetic data gen prompts. Since you've already defined a goal when setting up your task, Kiln can do this for you. It will infer the type of data needed from the system prompt, adapt it to your data-gen goal, and create synthetic data gen prompts without any manual prompting.

[Learn more below](references/docs/synthetic-data-generation.md#automatic-templates-and-custom-prompting)

### Walkthrough

#### Choose A Goal To Focus Data Gen

First select a goal for your dataset generation: Evals or Fine-Tuning. This is an important step as you need different data for different goals:

* **Fine-Tuning**: generate high quality outputs across a broad range of possible inputs, to help your model learn how to respond to a range of requests. This can include generating inputs that commonly produce issues, and outputs that avoid that issue.
* **Evals**: Intentionally generate a mix of good and bad inputs and outputs. We'll use the bad outputs to ensure the judge model can properly assess failures, and we'll use the bad inputs to ensure your task no longer has the issue.

Selecting the goal will set up two properties:

* **Template:** A Kiln prompt template to guide the data gen. You can edit this template before running data gen.
* **Tag Assignments:** which dataset tags will be assigned to generated data. This could be a single tag like `fine_tuning_data` or a randomly assigned split like `eval_data: 80%, golden_data: 20%`.

#### Choose A Data Gen Model

{% hint style="info" %}
**TL;DR:** Choose a high quality model like GPT 4o or Grok 4 for synthetic data gen. Synthetic data gen is complex, and benefits from larger models.
{% endhint %}

We highly recommend choosing a large capable model for data gen. While your task may work on smaller models, data gen is more complex. It requires reasoning about a range of possible inputs, probing edge cases, and more. It benefits from a large model with a long context.

If generating content to evaluate how your model responds to inappropriate requests (bias, jailbreaking, maliciousness, etc.), choose an uncensored model like Grok. Censored models like GPT 4o will refuse to generate some types of content.

#### Interactive Curation UX

Kiln synthetic data generation is designed to be interactive! As you work, be critical of the generated data and use the interactive UI to make great quality data. You can delete topics or examples that don't match your goals, add custom topics manually, update prompts to guide content, and iterate until you're happy with the results.

### 4 Stages of Data Gen: Topics, Inputs, Outputs, Saving

Kiln generates synthetic data in 4 stages:

* [**Topics**](references/docs/synthetic-data-generation.md#topic-tree-data-generation-for-content-breadth): generate a tree of topics, which allows for breadth
* [**Model Inputs**](references/docs/synthetic-data-generation.md#generate-model-inputs): generate synthetic model inputs (the user message). Optionally targeting a specific topic. Within each topic, we aim for a range of relevant inputs which are not too similar to each other.
* [**Model Outputs**](references/docs/synthetic-data-generation.md#generate-model-outputs): generate synthetic model outputs from one of the inputs.
* [**Save Data**](references/docs/synthetic-data-generation.md#save-synthetic-data-into-dataset): once you're happy with your synthetic data, save it into your dataset for use in evals and fine-tuning.

#### Topic Generation For Content Breadth

A common issue with synthetic data generation is that if you ask a model to generate synthetic data 1000 times, you get 1000 very similar outputs. Kiln addresses this by first generating a tree of diverse topics, then generating data targeting on individual topics.

Kiln can use AI models to generate a topic tree for you from your task's prompt. It uses the prompt to ensure the topics are relevant to your goal. See the example above, the model knew it was building topics for newspaper headlines and generated appropriate topics. To generate topics, click "Add Topics":

You can nest sub-topics under any topic, forming the tree. Adding layers allows you to quickly generate a significant amount of diverse data. Hover any topic's "..." menu to expose a "Add Subtopics" button:

You can manually add topics instead of using synthetic topic generation. Select the "or manually add topics" option at the bottom of the "Generate Topics" dialog.

Topics are strongly recommended, but are optional. You can skip topics and add model inputs without topics by clicking "Generate Model Inputs".

#### Generate Model Inputs

Model inputs are the data passed into your task. When normally running your task, these would likely come from a human. However, in synthetic data generation we use AI models to generate them.

Click "Generate Inputs" button to generate model inputs using an AI model:

This will produce inputs under each topic in your data table:

Review the quality of inputs and ensure you're happy with them before proceeding. You can delete individual inputs for manual curation, or delete them all, [edit the generation prompt with more guidance](references/docs/synthetic-data-generation.md#automatic-templates-and-custom-prompting), and then try generating again to get better quality data.

#### Generate Model Outputs

Once you have generated all of the inputs you want, click "Generate Outputs" to generate outputs to present options for generation:

Generating will result in outputs for each input:

Review the quality of outputs and ensure you're happy with them before proceeding. You can delete individual outputs for manual curation, or delete them all, [edit the generation prompt](references/docs/synthetic-data-generation.md#automatic-templates-and-custom-prompting) with more guidance, and then try generating again to get better quality data.

#### Save Synthetic Data into Dataset

Use the Kiln synthetic data UI to review your data. Once you're happy with the data, click "Save All" to save it into your dataset for use in evals and fine-tuning.

The data will automatically be tagged with appropriate tags, based on the goal you selected ([see details](references/docs/synthetic-data-generation.md#tagging)):

Once saved, you can view all of your saved data in the Dataset tab.

### Automatic Templates and Custom Prompting

When you select a goal, we'll select the corresponding prompt template. These are built into Kiln and help guide data generation for a variety of tasks.

When creating synthetic data for an eval there are two additional powerful options:

* Kiln Issue Template: When you create an eval using the "Issue" template, data gen will create a template that can help find passing and failing examples for evaluating and resolving the issue.
* Kiln Requirements Template: Generate synthetic data to evaluate overall task rating, and any requirements you added to your task.

{% hint style="info" %}
**You can edit templates or add custom prompts to get the desired behaviour**
{% endhint %}

These templates are a starting point. They may work for you out of the box, or you may want to edit them to get the desired data. You can edit a template before you run data gen to ensure it matches your needs.

Some examples of custom prompts/edits:

* Generate content for global topics, not only US-centric
* Generate examples in Spanish
* The model is having trouble classifying sentiment of sarcastic messages. Generate sarcastic messages.

{% hint style="info" %}
Often custom guidance is used for producing adversarial content: poor quality or inappropriate content. This is done to ensure an [evaluation](references/docs/evals-and-specs/evaluations.md) can detect and fail this sort of content.

However, LLMs will often do their best to avoid producing poor or inappropriate content, even when asked for it. If you find that's the case, use an uncensored and unaligned model like Dolphin 8x22B or Grok. These models will follow instructions more closely, and do not attempt to censor their content.
{% endhint %}

### Structured Data (JSON, tool calling)

If your task requires structured input and/or output, your synthetic data generation will automatically follow the schemas you defined. All values are validated against the schemas you define, and nothing will be saved into your dataset if they don't comply.

You can define the schema in our task definition UI for a visual schema builder. Alternatively you can directly set a JSON Schema in the task via our python library or a text editor.

Under the hood we attempt to use tool calling when the model supports it, but will fallback to JSON parsing if not.

### Resolving Bugs & Issues with Synthetic Data

Synthetic data is a great tool for resolving bugs and issues in AI systems.

Follow these steps:

1. Create an eval using the Issue template, which will ask you to describe the issue and optionally provide examples.
2. Use synthetic data generation, selecting that issue as the goal. Generate data that reproduces that issue, then return to evals and verify you now have an eval Judge + eval dataset that can detect the issue reliably.
3. Iterate on different approaches to solving the problem (adjust prompt, model, temperature), using your eval judge to check if the solution works
4. Optionally use synthetic data and fine-tuning to fix the issue (for difficult issues where prompting doesn't work). Select the issue as the goal, but modify the tag assignment to `fine_tuning_data`, generate problematic inputs with successful outputs, adding these pairs to your fine tuning dataset.

### Tagging

All synthetic data will be assigned a series of [tags](references/docs/organizing-datasets.md#using-tags-to-organize-your-dataset):

* The tag `synthetic` (manual and imported runs have their own tags)
* A unique tag to identify the data session (e.g. `synthetic_session_12345`)
* Custom tags. These are setup automatically when you select a goal, but you can edit before generating data:


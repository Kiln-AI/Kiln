---
description: Fine tuning 9 Models in 18 minutes
---

# Fine Tuning Guide

Kiln makes it easy to fine-tune a wide variety of models like GPT-4o, Llama, Mistral, Gemma, and many more.

### Overview

In this guide we'll be walking through an example where we start from scratch, and build 9 fine-tuned models in just under 18 minutes of active work, not counting time waiting for training and data-gen.

No coding is necessary, and our UI will guide you through the process. Step 6 is optional, and requires some basic python skills. Our open-source python library is available for advanced users.

You can follow this guide to create your own LLM fine-tunes. We'll cover:

A Demo Project:

* \[2 mins]: [Define task, goals, and schema](references/docs/fine-tuning/fine-tuning-guide.md#step-1-define-your-task-and-goals)
* \[9 mins]: [Synthetic data generation](references/docs/synthetic-data-generation.md): create 920 high-quality examples for training
* \[5 mins]: Dispatch 9 fine tuning jobs: [Fireworks](references/docs/fine-tuning/fine-tuning-guide.md#step-4-dispatch-training-jobs) (Llama 3.2 1b/3b/11b, Llama 3.1 8b/70b, Mixtral 8x7b), [OpenAI](references/docs/fine-tuning/fine-tuning-guide.md#step-4-dispatch-training-jobs) (GPT 4o, 4o-Mini), and [Unsloth](references/docs/fine-tuning/fine-tuning-guide.md#step-6-optional-training-on-your-own-infrastructure) (Llama 3.2 1b/3b). Note: since this guide was written we've added over 60 new models for fine tuning!
* \[2 mins]: [Deploy your new models and test they work](references/docs/fine-tuning/fine-tuning-guide.md#step-5-deploy-and-run-your-models)

Analysis:

* [Cost Breakdown](references/docs/fine-tuning/fine-tuning-guide.md#cost-breakdown)
* [Next steps](references/docs/fine-tuning/fine-tuning-guide.md#next-steps): evaluation, exporting models, iteration and data strategies

{% hint style="info" %}
If you want to tune a reasoning model, see our [guide for training reasoning models](references/docs/fine-tuning/guide-train-a-reasoning-model.md). It includes notes about each step of this guide which are necessary to produce a reasoning model.
{% endhint %}

### Step 1: Define your Task

First, we’ll need to define what the models should do. In Kiln we call this a “task definition”. Create a new task in the Kiln UI to get started, including a initial prompt and input/output schema.

For this demo we'll make a task that generates news article headlines of various styles, given a summary of a news topic.

{% embed url="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEJ4b8A4QiEQlOGbYkXDX%2Fuploads%2FL6pUgqBP3wgAhIZtfJ5L%2FCreateTask720.mp4?alt=media&token=1e8dcf3a-bb10-4774-a421-0fed5b0adb2e" %}
Create a task to fine-tune for
{% endembed %}

### Step 2: Generate Training Data with Synthetic Data Generation

To fine tune, you’ll need a dataset to learn from.

Kiln offers an interactive UI for quickly and easily building synthetic datasets. In the video below we use it to generate 920 training examples in 9 minutes of hands-on work. See our [data gen guide](references/docs/synthetic-data-generation.md) for more details.

{% hint style="info" %}
All fine tuning data must be tagged with a [tag](references/docs/organizing-datasets.md#using-tags-to-organize-your-dataset) starting with `fine_tune` (e.g. fine\_tune, fune\_tune\_thinking, fine\_tune\_experiment\_42).

If you launch synthetic data gen from within the "Create a New Fine Tune" screen, the tag `fine_tune` will automatically be added to all generated samples.&#x20;

If you already created tuning data, use the dataset tab to add the `fine_tune` tag to the samples you want to use for tuning.
{% endhint %}

Kiln includes topic trees to generate diverse content, a range of models/prompting strategies, interactive guidance and interactive UI for curation/correction.

When generating synthetic data you want to generate the best quality content possible. Don’t worry about cost and performance at this stage. Use large high quality models, detailed prompts with multi-shot prompting, chain of thought, and anything else that improves quality. You’ll be able to address performance and costs in later steps with fine tuning.

{% embed url="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEJ4b8A4QiEQlOGbYkXDX%2Fuploads%2FwVRCYmuIg1s2d38NLZ2t%2FDatagen720.mp4?alt=media&token=6d1a18c7-67a7-4062-8ac6-fb88525676e7" %}
Synthetic Data Generation
{% endembed %}

### Step 3: Select Models to Fine Tune

Kiln supports over 60 fine-tuneable models using three different service based tuning providers:

* Open AI: GPT 4.1, 4o, 4.1-mini and 4o-mini
* Google Gemini: Gemini 2.0 flash and Gemini 2.0 Pro
* Fireworks.ai: over 60 open weight models including Qwen 2.5, Llama 2/3.x, Deepseek V3/R1, QwQ, and more. See the [full list here](references/docs/models-and-ai-providers.md#additional-fine-tuneable-models).
* Together AI: Llama 3.1 8b/70b, Llama 3.2 1b/3b, Qwen2.5 14b/72b

{% hint style="success" %}
To see more options on the "Create Fine Tune" screen, connect API keys for the providers listed above in Settings.
{% endhint %}

For this demo we choose 9 models to experiment with.

### Step 4: Dispatch Training Jobs

Use the "Fine Tune" tab in the Kiln UI to kick off your fine-tunes. Simply select the models you want to train, select a dataset, and add any training parameters.

{% hint style="info" %}
**Training Reasoning/Thinking Model**

Kiln can train a reasoning model. See the guide on [training reasoning models](references/docs/fine-tuning/guide-train-a-reasoning-model.md).
{% endhint %}

{% embed url="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEJ4b8A4QiEQlOGbYkXDX%2Fuploads%2F90AZYx6JVoCYFrhHCTUx%2FCreateTrainingJobs720.mp4?alt=media&token=c0e76a1b-0f55-4297-85b9-b1f9b6c4125f" %}
Dispatching Training Jobs. Note: video does not match current UI
{% endembed %}

### Step 5: Deploy and Run Your Models

Kiln will automatically deploy your fine-tunes when they are complete. You can use them from the Kiln UI without any additional configuration. Simply select a fine-tune by name from the model dropdown in the "Run" tab.

Together, Fireworks and OpenAI tunes are deployed "serverless". You only pay for usage (tokens), with no recurring costs.

You can use your models outside of Kiln by calling Fireworks or OpenAI APIs with the model ID from the "Fine Tune" tab.

**Early Results**: Our fine-tuned models show some immediate promise. Previously models smaller than Llama 70b failed to produce the correct structured data for our task. After fine tuning even the smallest model, Llama 3.2 1b, consistently works.

{% embed url="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEJ4b8A4QiEQlOGbYkXDX%2Fuploads%2FevKBtLibJBN56hVGULL7%2FRun720.mp4?alt=media&token=f072c028-088b-4673-9d10-f88580d71cb7" %}
Running some of our Fine Tuned Models (Llama 3.2 1b & GPT 4o-mini)
{% endembed %}

{% hint style="info" %}
If a Fireworks fine tune gives you the error \`Model not found, inaccessible, and/or not deployed\`, it means that model was un-deployed by Fireworks. Opening the model in the "Fine Tune" tab of Kiln will trigger a re-deploy.
{% endhint %}

### Step 6 \[Optional]: Training on your own Infrastructure

Kiln can also export your dataset to common formats for fine tuning on your own infrastructure. Simply select one of the "Download" options when creating your fine tune, and use the exported JSONL file to train with your own tools.

We currently recommend [Unsloth](https://github.com/unslothai/unsloth) and Axolotl. These platforms let you train almost any open model, including Gemma, Mistral, Llama, Qwen, Smol, and [many more](https://docs.unsloth.ai/get-started/all-our-models).

**Unsloth Example**

See this example [Unsloth notebook](https://colab.research.google.com/drive/1Ivmt4rOnRxEAtu66yDs_sVZQSlvE8oqN?usp=sharing), which has been modified to load a dataset file exported from Kiln. You can use it to fine-tune locally or in Google Colab.

Export your dataset using the "Hugging Face chat template (JSONL)" option for compatibility with the demo notebook.

{% embed url="https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FEJ4b8A4QiEQlOGbYkXDX%2Fuploads%2Fsr97NzR4hJGsUWiIJPCv%2FUnsloth720.mp4?alt=media&token=041646ce-fbeb-4627-894b-1b4a20f27090" %}
Unsloth Demo
{% endembed %}

#### Google Gemini on Vertex AI

Kiln can generate the training format needed by Google's Vertex AI to fine tune Gemini models.

Select the Vertex AI/Gemini option in the dropdown, to download training/validation files in the appropriate format. Then follow the Google's fine-tuning [guide](https://cloud.google.com/vertex-ai/generative-ai/docs/models/tune-models), using the files from Kiln as your training/validation sets.

### Cost Breakdown

Our demo use case was quite reasonably priced.

| Task                                  | Platform                   | Cost (USD) |
| ------------------------------------- | -------------------------- | ---------- |
| Training Data Generation              | OpenRouter                 | $2.06      |
| Fine-tuning 5x Llama models + Mixtral | Fireworks                  | $1.47      |
| Fine-tuning GPT-4o Mini               | OpenAI                     | $2.03      |
| Fine-tuning GPT-4o                    | OpenAI                     | $16.91     |
| Fine-tuning Llama 3.2 (1b & 3b)       | Unsloth on Google Colab T4 | $0.00      |

If it wasn't for GPT-4o, the whole project would have cost less than $6!

Meanwhile our fastest fine-tune (Llama 3.2 1b) is about 10x faster and 150x cheaper than the models we used during synthetic data generation (source:OpenRouter perf stats & prices).

### Track Training Metrics with Weights & Biases

Kiln supports tracking training metrics with the tool [Weights & Biases](https://wandb.ai/site/) . Configure your W\&B API key in `Settings > AI Providers & Models > Weights & Biases` before starting your fine-tuning job. Metrics will appear for any training jobs on Fireworks or Together. OpenAI doesn't support W\&B, but provides similar metrics in their own dashboard, which is linked from the Kiln Fine Tune page.

<figure><img src="../../.gitbook/assets/Screenshot 2025-03-19 at 7.27.16 PM.png" alt="" width="287"><figcaption><p>Weights and Biases Metrics</p></figcaption></figure>

### Next Steps

What’s next after fine tuning?

#### **Evaluate Model Quality**

We now have 9 fine-tuned models, but which is best for our task? We should evaluate them for quality/speed/cost tradeoffs.

Kiln has [powerful evaluation tools](references/docs/evals-and-specs/evaluations.md) to help you though this process. Check out the [evaluation guide](references/docs/evals-and-specs/evaluations.md) for details.

If your task is deterministic (classification), Kiln AI will provide the validation set to OpenAI or Together during tuning, and they will report val\_loss on their dashboard. For non-deterministic tasks (including generative tasks) you can use our [evaluation tools](references/docs/evals-and-specs/evaluations.md) to evaluate quality.

#### **Exporting Models**

You can export your models for use on your machine, deployment to the cloud, or embedding in your product.

* Fireworks: you can [download the weights](https://docs.fireworks.ai/fine-tuning/fine-tuning-models#downloading-model-weights) in Hugging Face PEFT format, and convert as needed.
* Together: you can [download the weights](https://docs.together.ai/docs/finetuning#running-your-model-locally), run locally or convert as needed.
* Unsloth: your fine-tunes can be directly exported to GGUF or other formats which make these model easy to deploy. A GGUF can be [imported to Ollama](https://github.com/ollama/ollama/blob/main/docs/import.md) for local use. Once added to Ollama, the models will become available in Kiln UI as well.
* OpenAI: sadly OpenAI won’t let you download their models.

#### **Iterate to Improve Quality**

Models and products are rarely perfect on their first try. When you find bugs or have new goals, Kiln makes it easy to build new models. Some ways to iterate:

* Experiment with different base-models
* Experiment with fine-tuning hyperparameters (see the "Advanced Options" section of the UI)
* Experiment with shorter training prompts, which can reduce costs
* For one-off bugs you encounter use Kiln to “[repair](references/docs/repairing-responses.md)” the issues. These get added to your training data for future iterations.
* For recurring bugs/patterns, use [synthetic data generation](references/docs/synthetic-data-generation.md) to generate many samples of common bugs, ensure they have correct responses with [human guidance](references/docs/synthetic-data-generation.md#human-guidance), and add the results to the training set to prevent this class of issues in the future.
* Rate your dataset using Kiln’s [rating system](references/docs/reviewing-and-rating.md), then build fine-tunes using only highly rated content.
* Regenerate fine-tunes as your dataset grows and evolves
* Try new foundation models (directly and with fine tuning) when new state of the art models are released.

#### **Integrate with Code**

Kiln can be used entirely through the UI and doesn't require coding. However, if you'd like a code-based integration, our open-source [Python library](https://pypi.org/project/kiln-ai/) is available. You can dispatch fine-tune jobs and call fine-tuned models through our library without the UI if you prefer.

### **Our "Ladder" Data Strategy**

Kiln enables a "Ladder" data strategy: the steps start from small quantity and high effort, and progress to high quantity and low effort. Each step builds on the prior:

* \~10 manual high quality examples.
* \~30 LLM generated examples using the prior examples for multi-shot prompting. Use expensive models, detailed prompts, and token-heavy techniques (chain of thought). Manually review each ensuring low quality examples are not used as samples.
* \~1000 synthetically generated examples, using the prior content for multi-shot prompting. Again, using expensive models, detailed prompts and chain of thought. Some interactive sanity checking as we go, but less manual review once we have confidence in the prompt and quality.
* 1M+: after fine-tuning on our 1000 sample set, most inference happens on our fine-tuned model. This model is faster and cheaper than the models we used for building it through zero shot prompting, shorter prompts, and smaller models.

Like a ladder, skipping a step is dangerous. You need to make sure you’re solid before you continue to the next step.

# Guide: Fine Tuning 9 Models in 18 minutes with [Kiln AI](https://getkiln.ai)

[Kiln](https://getkiln.ai) is a new tool that makes it easy to fine-tune a wide variety of models like GPT-4o, Llama, Mistral, Gemma, and many more.

## Overview

We'll be walking through an example where we start from scratch, and build 9 fine-tuned models in just under 18 minutes of active work (not counting time waiting for training to complete).

You can follow this guide to create your own LLM fine-tunes. We'll cover:

A Demo Project:
- [2 mins]: [Define task, goals, and schema](#step-1-define-your-task-and-goals)
- [9 mins]: [Synthetic data generation](#step-2-generate-training-data-with-synthetic-data-generation): create 920 high-quality examples for training
- [5 mins]: Dispatch 9 fine tuning jobs: [Fireworks](#step-4-dispatch-training-jobs) (Llama 3.2 1b/3b/11b, Llama 3.1 8b/70b, Mixtral 8x7b), [OpenAI](#step-4-dispatch-training-jobs) (GPT 4o, 4o-Mini), and [Unsloth](#step-6-optional-training-on-your-own-infrastructure) (Llama 3.2 1b/3b)
- [2 mins]: [Deploy your new models and test they work](#step-5-deploy-and-run-your-models)

Analysis:
- [Cost Breakdown](#cost-breakdown)
- [Next steps](#next-steps): evaluation, exporting models, iteration and data strategies
- [How to get started](#download-kiln-to-get-started)

[<img width="190" alt="Download button" src="https://github.com/user-attachments/assets/09874d7a-4873-4bb7-81c8-c3939206dc81">](https://github.com/Kiln-AI/Kiln/releases/latest)

### Step 1: Define your Task and Goals

First, we’ll need to define what the models should do. In Kiln we call this a “task definition”. Create a new task in the Kiln UI to get started, including a initial prompt, requirements, and input/output schema.

For this demo we'll make a task that generates news article headlines of various styles from a summary of a news topic.

https://github.com/user-attachments/assets/5a7ed956-a797-4d8e-9ed9-2a9d98973e86

### Step 2: Generate Training Data with Synthetic Data Generation

To fine tune, you’ll need a dataset to learn from.

Kiln offers a interactive UI for quickly and easily building synthetic datasets. In the video below we use it to generate 920 training examples in 9 minutes of hands-on work. See our [data gen guide](https://github.com/Kiln-AI/Kiln/blob/main/guides/Synthetic%20Data%20Generation.md) for more details.

Kiln includes topic trees to generate diverse content, a range of models/prompting strategies, interactive guidance and interactive UI for curation/correction. 

When generating synthetic data you want to generate the best quality content possible. Don’t worry about cost and performance at this stage. Use large high quality models, detailed prompts with multi-shot prompting, chain of thought, and anything else that improves quality. You’ll be able to address performance and costs in later steps with fine tuning.

https://github.com/user-attachments/assets/f2142ff5-10ca-4a23-a88a-05e2bd24d641


### Step 3: Select Models to Fine Tune

Kiln supports a wide range of models from our UI, including:

- OpenAI: GPT 4o and 4o-Mini
- Meta:
  - Llama 3.1 8b/70b
  - Llama 3.2 1b/3b
- Mistral: Mixtral 8x7b MoE

In this demo, we'll use them all!

### Step 4: Dispatch Training Jobs

Use the "Fine Tune" tab in the Kiln UI to kick off your fine-tunes. Simply select the models you want to train, select a dataset, and add any training parameters.

We recommend setting aside a test and validation set when creating your dataset split. This will allow you to evaluate your fine-tunes after they are complete.

https://github.com/user-attachments/assets/e20af3f5-1e9e-4c55-a765-e1688782b7e2

### Step 5: Deploy and Run Your Models

Kiln will automatically deploy your fine-tunes when they are complete. You can use them from the Kiln UI without any additional configuration. Simply select a fine-tune by name from the model dropdown in the "Run" tab.

Both Fireworks and OpenAI tunes are deployed "serverless". You only pay by for usage (tokens), with no recurring costs.

You can use your models outside of Kiln by calling Fireworks or OpenAI APIs with the model ID from the "Fine Tune" tab.

**Early Results**: Our fine-tuned models show some immediate promise. Previously models smaller than Llama 70b failed to produce the correct structured data for our task. After fine tuning even the smallest model, Llama 3.2 1b, consistently works.

https://github.com/user-attachments/assets/2f64dd1d-a684-456f-8505-114defaff304


### Step 6 [Optional]: Training on your own Infrastructure

Kiln can also export your dataset to common formats for fine tuning on your own infrastructure. Simply select one of the "Download" options when creating your fine tune, and use the exported JSONL file to train with your own tools.

We currently recommend [Unsloth](https://github.com/unslothai/unsloth) and [Axolotl]([https://github.com/gw000/axolotl](https://axolotl.ai)). These platforms let you train almost any open model, including Gemma, Mistral, Llama, Qwen, Smol, and many more.

#### Unsloth Example

See this example [Unsloth notebook](https://colab.research.google.com/drive/1Ivmt4rOnRxEAtu66yDs_sVZQSlvE8oqN?usp=sharing), which has been modified to load a dataset file exported from Kiln. You can use it to fine-tune locally or in Google Colab.

https://github.com/user-attachments/assets/102874b0-9b85-4aed-ba4a-b2d47c03816f

### Cost Breakdown

Our demo use case was quite reasonably priced.

- Generating training data: $2.06 on OpenRouter
- Fine tuning 5 models on Fireworks (Llama 3.2 1b, Llama 3.2 3b, Llama 3.1 8b, Llama 3.1 70b, and Mixtral 8x7b): $1.47
- Fine tuning GPT 4o-Mini on OpenAI: $2.03
- Fine tuning GPT 4o on OpenAI: $16.91
- Fine tuning Llama 3.2 1b & 3b on Unsloth: $0.00 (free Google Colab T4)

If it wasn't for GPT-4o, the whole project would have cost less than $6!

Meanwhile our fastest fine-tune (Llama 3.2 1b) is about 10x faster and 150x cheaper than the models we used during synthetic data generation (source:OpenRouter perf stats & prices). 

### Next Steps

What’s next after fine tuning?

#### Evaluate Model Quality

We now have 9 fine-tuned models, but which is best for our task? We should evaluate their quality for quality/speed/cost tradeoffs.

We will be adding eval tools into Kiln soon to help with this process! In the meantime, you can used the reserved test/val splits to evaluate the fine tunes. 

If your task is deterministic (classification), Kiln AI will provide the validation set to OpenAI during tuning, and OpenAI will report val_loss on their dashboard. For non-deterministic tasks (including generative tasks) you'll need to use human evaluation.

<img width="339" alt="OpenAI val_acc" src="https://github.com/user-attachments/assets/3f39d02a-93bd-4fd1-8eba-9e2a3f61ea5f">


#### Exporting Models

You can export your models for use on your machine, deployment to the cloud, or embedding in your product.

 - Fireworks:you can [download the weights](https://docs.fireworks.ai/fine-tuning/fine-tuning-models#downloading-model-weights) in Hugging Face PEFT format, and convert as needed.
 - Unsloth: your fine-tunes can be directly export to GGUF or other formats which make these model easy to deploy. A GGUF can be [imported to Ollama](https://github.com/ollama/ollama/blob/main/docs/import.md) for local use.
 - OpenAI: sadly OpenAI won’t let you download their models.

#### Iterate to Improve Quality

Models and products are rarely perfect on their first try. When you find bugs or have new goals, Kiln makes it easy to build new models. Some ways to iterate:

- Experiment with fine-tuning hyperparameters (see the "Advanced Options" section of the UI)
- Experiment with shorter training prompts, which can reduce costs
- Add any bugs you encounter to your dataset, using Kiln to “repair” the issues. These get added to your training data for future iterations.
- Rate your dataset using Kiln’s rating system, then build fine-tunes using only highly rated content.
- Generate  synthetic data targeting common bugs you see, so the model can learn to avoid those issues
- Regenerate fine-tunes as your dataset grows and evolves
- Try new foundation models (directly and with fine tuning) when new state of the art models are released.

#### Our "Ladder" Data Strategy

Kiln enables a "Ladder" data strategy: the steps start from from small quantity and high effort, and progress to high quantity and low effort. Each step builds on the prior:

- ~10 manual high quality examples
- ~30 LLM generated examples using the prior examples for multi-shot prompting. Use expensive models, detailed prompts, and token-heavy techniques (chain of thought). Manually review each ensuring low quality examples are not used as samples.
- ~1000 synthetically generated examples, using the prior content for multi-shot prompting. Again, using expensive models, detailed prompts and chain of thought. Some interactive sanity checking as we go, but less manual review once we have confidence in the prompt and quality.
- 1M+: after fine-tuning on our 1000 sample set, most inference happens on our fine-tuned model. This model is faster and cheaper than the models we used for building it through zero shot prompting, shorter prompts, and smaller models.

Like a ladder, skipping a step is dangerous. You need to make sure you’re solid before you to the next step.

### Download Kiln to Get Started

To get started, download Kiln. It’s 100% free:

- Star us on [Github](https://github.com/Kiln-AI/Kiln)
- Read more about Kiln in our [Github Readme](https://github.com/Kiln-AI/Kiln?tab=readme-ov-file#readme)

[<img width="190" alt="Download button" src="https://github.com/user-attachments/assets/09874d7a-4873-4bb7-81c8-c3939206dc81">](https://github.com/Kiln-AI/Kiln/releases/latest)




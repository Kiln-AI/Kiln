# Fine Tuning with Kiln AI - Guide

[Kiln](https://getkiln.ai) is a tool that makes it easy to fine-tune a wide variety of models like GPT-4o, Llama, Mistral, Gemma, and much more.

## Overview

We'll be walking through an example where we start from scratch, and build 9 fine-tuned models in just under 18 minutes of active work (not counting time waiting for training to complete).

You can follow this guide to create your own LLM fine-tunes. We'll cover:

- [2 mins]: Define task, goals, and schema
- [9 mins]: Synthetic data generation: create 920 high-quality examples for training
- [5 mins]: kick off 9 fine tuning jobs: Unsloth (Llama 3.1 8b), OpenAI (GPT 4o, 4o-Mini), and Fireworks (Llama 3.2 1b/3b/11b, Llama 3.1 8b/70b, Mixtral 8x7b)
- [2 mins]: Test that our new models work

### Step 1: Define your Task and Goals

First, we’ll need to define what the models should do. In Kiln we call this a “task definition”. Create a new task in the Kiln UI to get started, including a initial prompt, requirements, and input/output schema.

https://github.com/user-attachments/assets/5a7ed956-a797-4d8e-9ed9-2a9d98973e86

### Step 2: Generate Training Data (including Synthetic Data Gen)

To fine tune, you’ll need a dataset to learn from.

Kiln offers a interactive UI for quickly and easily building synthetic datasets. It includes topic trees to generate diverse content, a range of models/prompting strategies, interactive guidance and interactive UI for curation and correction. In the video below we use it to generate 920 training examples in 9 minutes of hands on work.

Note: when generating synthetic data you want to get the best quality content possible. Don’t worry about cost and performance at this stage. Use large high quality models, detailed prompts with multi-shot prompting, chain of thought, and anything else that improves quality. You’ll be able to address performance and costs in later steps with fine tuning.


https://github.com/user-attachments/assets/f2142ff5-10ca-4a23-a88a-05e2bd24d641


### Step 3: Select Models to Fine Tune

Kiln supports a wide range of models using our no-code UI, including:

- OpenAI: GPT 4o and 4o-Mini
- Meta:
  - Llama 3.1 8b/70b
  - Llama 3.2 1b/3b
- Mistral: Mixtral 8x7b MoE

In this demo, we'll use them all!

### Step 4: Kick off Training Jobs

Use the "Fine Tune" tab in the Kiln UI to kick off your fine-tunes. Simply select the models you want to train, the dataset, and add any training parameters.

We recommend setting aside a test and validation set when creating your dataset split. This will allow you to evaluate your fine-tunes after they are complete.

https://github.com/user-attachments/assets/e20af3f5-1e9e-4c55-a765-e1688782b7e2

### Step 5: Deploy and Run Your Models

Kiln will automatically deploy your fine-tunes when they are complete. You can use them from the Kiln UI without any additional configuration, or call them through OpenAI or Fireworks APIs.

Both providers are deployed as "serverless" services. You only pay by token usage, with no recurring costs.

Our fine-tuned models show some immediate promise. Previously models smaller than Llama < 70b could not produce the correct structured data format, but after fine tuning even the smallest model (Llama 3.2 1b) consistently works.

https://github.com/user-attachments/assets/2f64dd1d-a684-456f-8505-114defaff304


### Step 6 [Optional]: Training on your own Infrastructure

Kiln can also export your dataset to common formats, for fine tuning on your own infrastructure. Simply select one of the "Download" options when creating your fine tune, and use the exported JSONL file to train with your own tools.

We currently recommend [Unsloth](https://github.com/unslothai/unsloth) and [Axolotl]([https://github.com/gw000/axolotl](https://axolotl.ai)).

#### Unsloth Example

See this example [unsloth notebook](https://colab.research.google.com/drive/1Ivmt4rOnRxEAtu66yDs_sVZQSlvE8oqN?usp=sharing), which has been modified to load a dataset file exported from Kiln. You can use it to fine-tune locally or in Google Colab.

https://github.com/user-attachments/assets/102874b0-9b85-4aed-ba4a-b2d47c03816f

### Total Costs

Our demo use case was quite reasonably priced.

- Generating training data: $2.06 on OpenRouter
- Fine tuning Llama 3.2 1b, Llama 3.2 3b, Llama 3.1 8b, Llama 3.1 70b, and Mixtral 8x7b on Fireworks: $1.47
- Fine tuning GPT 4o-Mini on OpenAI: $2.03
- Fine tuning GPT 4o on OpenAI: $16.91
- Fine tuning Llama/Gemma on Unsloth: $0.00 (free Google Colab T4)

If it wasn't for GPT-4o, the whole project would have less than $6!

Meanwhile our fastest fine-tune (Llama 3.2 1b) is about 10x faster and 200x cheaper than our initial

### Next Steps

What’s next after fine tuning?

#### Evaluate Model Quality

We now have 9 fine-tuned models, but which is best for our task? We should evaluate their quality for quality/speed/cost tradeoffs. 

We will be adding eval tools into Kiln soon to help with this process! In the meantime, you can used the reserved test/val splits to evaluate the fine tunes.

#### Exporting Models

You can export your models for use on your machine, deployment to the cloud, or embedding in your product.

**Unsloth**: your fine-tunes can be directly export to GGUF or other formats which make these model easy to deploy. A GGUF can be [imported to Ollama](https://github.com/ollama/ollama/blob/main/docs/import.md) for local use.

**Fireworks**:you can [download the weights](https://docs.fireworks.ai/fine-tuning/fine-tuning-models#downloading-model-weights) in Hugging Face PEFT format, and convert as needed.

Sadly, OpenAI won’t let you download their models.

#### Iterate to improve quality

Models and products are rarely perfect on their first try. When you find bugs or have new goals, Kiln makes it easy to build new models. Some ways to iterate:

- Experiment with fine-tuning hyperparameters (see the "Advanced Options" section of the UI)
- Experiment with shorter training prompts, which can reduce costs
- Add any bugs you encounter to your dataset, using Kiln to “repair” the issues. These get added to your training data for future iterations.
- Rate your dataset using Kiln’s rating system, then build fine-tunes using only highly rated content.
- Generate more synthetic data for common quality issues, so the model can learn to avoid them
- Regenerate fine-tunes as your dataset grows
- Try new foundation models (directly and with fine tuning) when new state of the art models are released.

### Get Kiln to Get Started

To get started, download Kiln. It’s 100% free:

- Star us on [Github](https://github.com/Kiln-AI/Kiln)
- [Download the latest Kiln AI release](https://github.com/Kiln-AI/Kiln/releases/latest)
- Read more about Kiln in our [Github Readme](https://github.com/Kiln-AI/Kiln?tab=readme-ov-file#readme)



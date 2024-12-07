# Synthetic Data Generation - Kiln AI 

[Kiln](https://getkiln.ai) can generate synthetic data for your tasks. 

## Video Walkthrough

<img src="https://github.com/user-attachments/assets/eab36818-2c88-4e52-ac39-a71c40e5cc79" width="520"/>

## Use Cases

Synthetic data is helpful for many reasons:

- To generate a dataset for fine-tuning
- To generate examples to be used for few-shot or multi-shot prompting
- To test your task in a controlled environment
- To generate eval datasets
- To generate targeted data to reproduce a bug/issue, which can be used for training a fix, evaluating a fix, and backtesting

## How it works

### Zero-Shot Data Generation

Once you've created a Kiln task defining your goals, data generation will use it to generate synthetic data without any additional configuration.

### Topic-Tree Data Generation

To generate a breadth of examples, Kiln can generate a topic tree and generate examples for each node. This includes nested topics, which allows you to generate a lot of broad data very quickly.

You can use automatic topic generation, or manually add topics to your topic tree.

### Human Guidance

Sometimes you may want to guide the generation process to ensure that the data generated matches your needs. You can add human guidance to your data generation task at any time.

Adding a short guidance prompt can quickly improve the quality of the generated data. Some examples:

- Generate content for global topics, not only US-centric
- Generate examples in Spanish
- The model is having trouble classifying sediment of sarcastic messages. Generate sarcastic messages.

### Interactive Curation UX

Kiln synthetic data generation is designed to be used in our interactive UI.

As you work, delete topics or examples that don't match your goals, and regenerate the data until you're happy with the results. Adding human guidance can help with this process.

[<img width="190" alt="Download button" src="https://github.com/user-attachments/assets/09874d7a-4873-4bb7-81c8-c3939206dc81">](https://github.com/Kiln-AI/Kiln/releases/latest)

### Structured Data Generation (JSON, tool calling)

If your task requires structured input and/or output, your synthetic data generation will automatically follow the schemas you defined. All values are validated against the schemas you define, and nothing will be saved into your dataset if they don't comply.

You can define the schema in our task definition UI for a visual schema builder. Alternatively you can directly set a JSON Schema in the task via our python library or a text editor.

Under the hood we attempt to use tool calling when the model supports it, but will fallback to JSON parsing if not.

### Generation Options

Kiln offers a number of options when generating a dataset:

- Model: which model to use for generation. We support a wide range of models (OpenAI, Anthropic, Llama, Google, Mistral, etc.) and a range of hosts including Ollama. Note: each model you see in the UI has been tested with the data generation tasks.
- Prompt: after rating a few examples, more powerful prompt options will open up for data generation. These include few-shot, multi-shot, chain-of-thought prompting, and more.

## Iteration

You can use synthetic data generation as many times as you'd like. Data will be appended to your dataset.

This can be useful for updating your dataset for new examples (e.g. fixing a bug/issue, or adding new use-cases).

## Collaboration

Kiln's dataset is designed to be collaborative. Subject matter experts, PM and QA can be generating and rating data, while data scientists can be reviewing and merging data.

The dataset format is designed to be Git friendly, including:

- UUIDs to avoid conflicts when many people are working in parallel
- Data formats that work well with diff tools
- Internal attribution (created_by tags), which makes it possible to allow non-technical team members to use a branch on a shared drive (if Git isn't their thing)

## Reviewing and Rating Data

Kiln includes a rating interface for rating dataset entries. This can be used to score the quality of the generated data, or to score the quality of a model.

Only highly rated data will be used for features like multi-shot prompting.

<img width="337" alt="rating UI" src="https://github.com/user-attachments/assets/6872d5ad-18ad-46f3-9091-2e26741cb852">


## Consuming Your Dataset

You can consume your dataset in a few different ways:

- In the 'Dataset' tab of Kiln's UI
- In the 'Prompts' tab of Kiln's UI for select prompts (few-shot, multi-shot and their variations)
- Via the [`kiln-ai` python library](https://pypi.org/project/kiln-ai/), which can be incorporated into any notebook or python project
- Via the Kiln OpenAPI REST API, which is served when running the Kiln Desktop app, and is also available as a standalone [python library `kiln-server`](https://pypi.org/project/kiln-server/)
- Direct filesystem access: the dataset is simply a directory of JSON files, so you can read it however you'd like

## Synthetic Data Generation From Code

Kiln includes a python library for data generation, which can be used to generate data from code. See our [python library docs](https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai/adapters/data_gen/data_gen_task.html) for more information.

# Get Started

See our [main Github Readme](https://github.com/Kiln-AI/Kiln?tab=readme-ov-file#readme) for more information on how to get started with Kiln.

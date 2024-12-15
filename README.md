<p align="center">
    <picture>
        <img width="205" alt="Kiln AI Logo" src="https://github.com/user-attachments/assets/5fbcbdf7-1feb-45c9-bd73-99a46dd0a47f">
    </picture>
</p>
<h3 align="center">
    The easiest tool for fine-tuning LLM models, synthetic data generation, and collaborating on datasets.
</h3>

|         |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CI      | [![Build and Test](https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml) [![Format and Lint](https://github.com/Kiln-AI/kiln/actions/workflows/format_and_lint.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/format_and_lint.yml) [![Desktop Apps Build](https://github.com/Kiln-AI/kiln/actions/workflows/build_desktop.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/build_desktop.yml) [![Web UI Build](https://github.com/Kiln-AI/kiln/actions/workflows/web_format_lint_build.yml/badge.svg)](https://github.com/Kiln-AI/kiln/actions/workflows/web_format_lint_build.yml) [![Test Count Badge](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/scosman/57742c1b1b60d597a6aba5d5148d728e/raw/test_count_kiln.json)](https://github.com/Kiln-AI/kiln/actions/workflows/test_count.yml) [![Test Coverage Badge](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/scosman/57742c1b1b60d597a6aba5d5148d728e/raw/library_coverage_kiln.json)](https://github.com/Kiln-AI/kiln/actions/workflows/test_count.yml) [![Docs](https://github.com/Kiln-AI/Kiln/actions/workflows/build_docs.yml/badge.svg)](https://github.com/Kiln-AI/Kiln/actions/workflows/build_docs.yml) |
| Package | [![PyPI - Version](https://img.shields.io/pypi/v/kiln-ai.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/kiln-ai/) [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kiln-ai.svg?logo=python&label=Python&logoColor=gold)](https://pypi.org/project/kiln-ai/)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Meta    | [![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv) [![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![Hatch project](https://img.shields.io/badge/%F0%9F%A5%9A-Hatch-4051b5.svg)](https://github.com/pypa/hatch) [![types - Pyright](https://img.shields.io/badge/types-pyright-blue.svg)](https://github.com/microsoft/pyright) [![Docs](https://img.shields.io/badge/docs-pdoc-blue)](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Apps    | [![MacOS](https://img.shields.io/badge/MacOS-black?logo=apple)](https://github.com/Kiln-AI/Kiln/releases/latest) [![Windows](https://img.shields.io/badge/Windows-0067b8.svg?logo=data:image/svg%2bxml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz4KPHN2ZyBmaWxsPSIjZmZmIiB2aWV3Qm94PSIwIDAgMzIgMzIiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTE2Ljc0MiAxNi43NDJ2MTQuMjUzaDE0LjI1M3YtMTQuMjUzek0xLjAwNCAxNi43NDJ2MTQuMjUzaDE0LjI1NnYtMTQuMjUzek0xNi43NDIgMS4wMDR2MTQuMjU2aDE0LjI1M3YtMTQuMjU2ek0xLjAwNCAxLjAwNHYxNC4yNTZoMTQuMjU2di0xNC4yNTZ6Ij48L3BhdGg+Cjwvc3ZnPg==)](https://github.com/Kiln-AI/Kiln/releases/latest) [![Linux](https://img.shields.io/badge/Linux-Experimental-blue)](https://github.com/Kiln-AI/Kiln/releases/latest)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

[<img width="220" alt="Download button" src="https://github.com/user-attachments/assets/a5d51b8b-b30a-4a16-a902-ab6ef1d58dc0">](https://github.com/Kiln-AI/Kiln/releases/latest)

## Key Features

- 🚀 **Intuitive Desktop Apps**: One-click apps for Windows, MacOS, and Linux. Truly intuitive design.
- 🎛️ **Fine Tuning**: Zero-code fine-tuning for Llama, GPT4o, and Mixtral. Automatic serverless deployment of models.
- 🤖 **Synthetic Data Generation**: Generate training data with our interactive visual tooling.
- 🤝 **Team Collaboration**: Git-based version control for your AI datasets. Intuitive UI makes it easy to collaborate with QA, PM, and subject matter experts on structured data (examples, prompts, ratings, feedback, issues, etc.).
- 📝 **Auto-Prompts**: Generate a variety of prompts from your data, including chain-of-thought, few-shot, and multi-shot.
- 🌐 **Wide Model and Provider Support**: Use almost any model via Ollama, OpenAI, OpenRouter, Fireworks, Groq, or AWS.
- 🧑‍💻 **Open-Source Library and API**: Our Python library and OpenAPI REST API are MIT open source.
- 🔒 **Privacy-First**: We can't see your data. Bring your own API keys or run locally with Ollama.
- 🗃️ **Structured Data**: Build AI tasks that speak JSON.
- 💰 **Free**: Our apps are free, and our library is open-source.

## Demo

In this demo, I create 9 fine-tuned models (including Llama 3.x, Mixtral, and GPT-4o-mini) in just 18 minutes, achieving great results for less than $6 total cost. [See details](guides/Fine%20Tuning%20LLM%20Models%20Guide.md).

<a href="guides/Fine%20Tuning%20LLM%20Models%20Guide.md">
<img alt="Kiln Preview" src="https://github.com/user-attachments/assets/51db632b-be98-4fc6-a31c-0ba6fd54dcbb">
</a>

## Download Kiln Desktop Apps

The Kiln desktop app is completely free. Available on MacOS, Windows and Linux.

[<img width="220" alt="Download button" src="https://github.com/user-attachments/assets/a5d51b8b-b30a-4a16-a902-ab6ef1d58dc0">](https://github.com/Kiln-AI/Kiln/releases/latest)

## Install Python Library

[![PyPI - Version](https://img.shields.io/pypi/v/kiln-ai.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/kiln-ai/) [![Docs](https://img.shields.io/badge/docs-pdoc-blue)](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html)

Our open-source [python library](https://pypi.org/project/kiln-ai/) allows you to integrate Kiln datasets into your own workflows, build fine tunes, use Kiln in Notebooks, build custom tools, and much more! [Read the docs](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html).

```bash
pip install kiln-ai
```

## Guides

- [Fine Tuning LLM Models Guide](guides/Fine%20Tuning%20LLM%20Models%20Guide.md)
- [Synthetic Data Generation Guide](guides/Synthetic%20Data%20Generation.md)
- [Using the Kiln Python Library](https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html) - Includes how to load datasets into Kiln, or using Kiln datasets in your own projects/notebooks.

## Learn More

### Build High Quality AI Products with Datasets

Products don’t naturally have “datasets”, but Kiln helps you create one.

Every time you use Kiln, we capture the inputs, outputs, human ratings, feedback, and repairs needed to build high quality models for use in your product. The more you use it, the more data you have.

Your model quality improves automatically as the dataset grows, by giving the models more examples of quality content (and mistakes).

If your product goals shift or new bugs are found (as is almost always the case), you can easily iterate the dataset to address issues.

### Collaborate Across Technical and Non-Technical Teams

When building AI products, there’s usually a subject matter expert who knows the problem you are trying to solve, and a different technical team assigned to build the model. Kiln bridges that gap as a collaboration tool.

Subject matter experts can use our easy to use desktop apps to generate structured datasets and ratings, without coding or using technical tools. No command line or GPU required.

Data-scientists can consume the dataset created by subject matter experts, using the UI, or dive deep with our python library.

QA and PM can easily identify issues sooner and help generate the dataset content needed to fix the issue at the model layer.

The dataset file format is designed to be be used with Git for powerful collaboration and attribution. Many people can contribute in parallel; collisions are avoided using UUIDs, and attribution is captured inside the dataset files. You can even share a dataset on a shared drive, letting completely non-technical team members contribute data and evals without knowing Git.

### Compare Models and Techniques Without Code

There are new models and techniques emerging all the time. Kiln makes it easy to try a variety of approaches, and compare them in a few clicks, without writing code. These can result in higher quality, or improved performance (smaller/cheaper/faster models at the same quality).

Our current beta supports:

- Various prompting techniques: basic, few-shot, multi-shot, repair & feedback
- Many models: GPT, Llama, Claude, Gemini, Mistral, Gemma, Phi
- Chain of thought prompting, with optional custom “thinking” instructions

In the future, we plan to add more powerful no-code options like fine tuning, lora, evals, and RAG. For experienced data-scientists, you can create these techniques today using Kiln datasets and our python library.

### Structured Data

We prioritize data correctness, which makes integrating into AI products easier. No data gets into the dataset without first passing validation, which keeps the dataset clean.

Our easy to use schema UI lets you create and use structured schemas, without knowing JSON-schema formatting. For technical users, we support any valid JSON-schema for inputs and outputs.

### Privacy

Your data stays completely private and local to your machine. We never collect or have access to:

- Datasets / Training Data
- API keys
- Model inputs/outputs (runs)

You can run completely locally using Ollama, or bring your own keys for OpenAI, OpenRouter, Groq, AWS, etc.

_Note: We collect anonymous usage metrics via Posthog analytics (never including dataset content or PII). This can be blocked with standard ad-blockers._

## REST API

[![PyPI - Version](https://img.shields.io/pypi/v/kiln-server.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/kiln-server/) [![Docs](https://img.shields.io/badge/docs-OpenAPI-blue)](https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.html)

We offer a self-hostable REST API for Kiln based on FastAPI. [Read the docs](https://kiln-ai.github.io/Kiln/kiln_server_openapi_docs/index.htm).

The REST API supports OpenAPI, so you can generate client libraries for almost [any](https://github.com/swagger-api/swagger-codegen) [language](https://openapi-generator.tech/docs/generators).

```bash
pip install kiln_server
```

## Contributing & Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for information on how to setup a development environment and contribute to Kiln.

## Licenses & Trademarks

- Python Library: [MIT License](libs/core/LICENSE.txt)
- Python REST Server/API: [MIT License](libs/server/LICENSE.txt)
- Desktop App: free to download and use under our [EULA](app/EULA.md), and [source-available](/app). [License](app/LICENSE.txt)
- The Kiln names and logos are trademarks of Chesterfield Laboratories Inc.

Copyright 2024 - Chesterfield Laboratories Inc.

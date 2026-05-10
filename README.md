<p align="center">
    <a href="https://kiln.tech">
        <picture>
            <img width="205" alt="Kiln AI Logo" src="https://github.com/user-attachments/assets/4ca9b69f-1c90-43a4-8d2e-13de4eb2ee9c">
        </picture>
    </a>
</p>

<h4 align="center">
  A free app and open-source library to build better AI products.
</h4>

<p align="center">
  <a href="https://kiln.tech#demo">
    <img width="420" alt="Kiln AI Animated Preview" src="https://github.com/user-attachments/assets/56ac04ea-010b-40bf-851c-ec5e05965336">
  </a>
</p>

<p align="center">
  <a href="https://kiln.tech/download"><img width="180" src="https://github.com/user-attachments/assets/a5d51b8b-b30a-4a16-a902-ab6ef1d58dc0" alt="Download Kiln"></a>
  <a href="https://docs.kiln.tech"><img width="180" src="https://github.com/user-attachments/assets/aff1b35f-72c0-4286-9b28-40a415558359" alt="Read the Docs"></a>
</p>


<p align="center">
  <a href="#highlights"><strong>Highlights</strong></a> •
  <a href="https://docs.kiln.tech/docs/evaluations"><strong>Evals</strong></a> •
  <a href="https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer"><strong>Auto-Optimize</strong></a> •
  <a href="https://docs.kiln.tech/docs/documents-and-search-rag"><strong>RAG</strong></a> •
  <a href="https://docs.kiln.tech/docs/agents"><strong>Agents</strong></a> •
  <a href="https://docs.kiln.tech/docs/fine-tuning-guide"><strong>Fine-Tuning</strong></a> •
  <a href="https://docs.kiln.tech/docs/synthetic-data-generation"><strong>Synthetic Data</strong></a> •
  <a href="https://docs.kiln.tech"><strong>All Docs</strong></a>
</p>

<p align="center">
  <a href="https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml"><img src="https://github.com/Kiln-AI/kiln/actions/workflows/build_and_test.yml/badge.svg" alt="Build and Test"></a>
  <a href="https://pypi.org/project/kiln-ai/"><img src="https://img.shields.io/pypi/v/kiln-ai.svg?logo=pypi&label=PyPI&logoColor=gold" alt="PyPI"></a>
  <a href="https://kiln.tech/discord"><img src="https://img.shields.io/badge/Discord-Kiln_AI-blue?logo=Discord&logoColor=white" alt="Discord"></a>
</p>

## What is Kiln?

Kiln is a workbench for the full AI development loop: evals, optimization, RAG, fine-tuning, synthetic data, agents, and tools — all working together. The desktop app lets your whole team contribute (PMs, subject-experts, and QA can rate outputs and add data without writing code). The MIT-licensed Python library ships the same tasks to production. Runs locally — bring your own API keys, or go fully offline with Ollama.

## Highlights

### Iterate, optimize, and collaborate

- 🖥️ [**Easy-to-use app**](https://kiln.tech/download) — One-click apps for Mac, Windows, and Linux.
- 📊 [**Eval Builder**](https://docs.kiln.tech/docs/evaluations) — Auto-generate evals (judge + synthetic eval dataset), and align to your preference in ~10 minutes. 
- 🚀 [**Auto-Optimize**](https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer) — Automatically find the best way to run your AI task, optimizing prompt, model selection, tools, skills, subagents, parameters, and more.
- 💬 [**AI Assistant**](https://docs.kiln.tech) — Your AI data-science partner. Kiln Assistant proposes improvements, optimizes prompts, runs experiments, creates evals, and more.
- 🪄 [**Synthetic Data Generation**](https://docs.kiln.tech/docs/synthetic-data-generation) — Generate data for evals or fine-tuning in minutes.
- 🤝 [**Git-native collaboration**](https://docs.kiln.tech/docs/collaboration) — The app syncs to Git automatically — even for teammates who don't know what Git is.

### Build & ship agents

- 🔍 [**RAG**](https://docs.kiln.tech/docs/documents-and-search-rag) — Drag-and-drop docs (PDF, image, video, audio), hybrid search via LanceDB, and auto-generated RAG evals from your own documents.
- 🤖 [**Subagents**](https://docs.kiln.tech/docs/agents) — Compose multi-agent hierarchies by turning any Kiln task into a callable subagent — each runs in its own focused context window.
- 🎛️ [**Fine-Tuning**](https://docs.kiln.tech/docs/fine-tuning-guide) — Zero-code fine-tuning across 60+ models (Qwen, Llama, GPT, Gemini, …) on Fireworks, Together, OpenAI, and Vertex — serverless deployment included.
- 🐍 [**Open Python library**](https://docs.kiln.tech/developers/python-library-quickstart) — Build in the app, deploy in production. Same engine, same project files, no rewrite. `pip install kiln-ai` · MIT.
- 🧰 [**…and more**](https://docs.kiln.tech) — Tools & MCP, Skills, structured outputs, reasoning models, model library (190+ tested).

## App Quickstart

Get started in minutes — no GPU, no terminal, no setup.

Download Kiln Desktop for macOS, Windows, or Linux, then follow the [5-minute quickstart](https://docs.kiln.tech/getting-started/quickstart) to run your first task.

[![MacOS](https://img.shields.io/badge/MacOS-black?logo=apple)](https://kiln.tech/download) [![Windows](https://img.shields.io/badge/Windows-0067b8.svg?logo=data:image/svg%2bxml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz4KPHN2ZyBmaWxsPSIjZmZmIiB2aWV3Qm94PSIwIDAgMzIgMzIiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTE2Ljc0MiAxNi43NDJ2MTQuMjUzaDE0LjI1M3YtMTQuMjUzek0xLjAwNCAxNi43NDJ2MTQuMjUzaDE0LjI1NnYtMTQuMjUzek0xNi43NDIgMS4wMDR2MTQuMjU2aDE0LjI1M3YtMTQuMjU2ek0xLjAwNCAxLjAwNHYxNC4yNTZoMTQuMjU2di0xNC4yNTZ6Ij48L3BhdGg+Cjwvc3ZnPg==)](https://kiln.tech/download) [![Linux](https://img.shields.io/badge/Linux-444444?logo=linux&logoColor=ffffff)](https://kiln.tech/download)

<sub>Prefer to start in code? See the [library quickstart](https://docs.kiln.tech/developers/python-library-quickstart).</sub>

## Demo

[Watch a 2-minute overview](https://kiln.tech#demo), or our [end-to-end project demo (20 minutes)](https://docs.kiln.tech/docs/end-to-end-project-demo).

## Open-source Python Library

Build in the app. Deploy with the open-source library. Same engine, same project files, no rewrite. The MIT-licensed `kiln-ai` library has full feature parity with the app — load Kiln projects, run tasks, build fine-tunes, work in notebooks, integrate Pandas/Polars dataframes, and more.

```bash
pip install kiln-ai
```

[📚 Library docs](https://docs.kiln.tech/developers/python-library-quickstart) · [REST API](https://docs.kiln.tech/developers/rest-api) · [PyPI](https://pypi.org/project/kiln-ai/)

## Why Kiln?

Most AI tooling forces a tradeoff: a code-only framework that covers one slice (orchestration *or* evals *or* RAG), or a paid SaaS that locks in your data. Kiln is a free, local-first workbench where a single task and dataset flow through evals, prompt optimization, fine-tuning, RAG, agents, and synthetic data — all in one tool.

- **One dataset, every technique.** Define a task once. Eval it, optimize the prompt, fine-tune a model, generate synthetic data, add RAG — all against the same dataset, with results that compound across stages.

- **Track every axis. Move fast. Don't regress.** Keeping agents running well is hard — a prompt change quietly regresses behavior three steps downstream; a model upgrade improves five things and breaks two. Kiln tracks quality across every dimension you care about, so you iterate without breaking what already works.

  <p align="center">
    <img width="600" alt="Kiln optimization across iterations" src="https://github.com/user-attachments/assets/5517b33b-74dd-444a-9f40-6a9c6d8a1ffc">
  </p>

- **Optimization, not just evaluation.** Promptfoo and OpenAI Evals tell you how a prompt scores. DSPy compiles prompts but requires its own programming model. Auto-Optimize generates evals from your spec, then searches across hundreds of prompt mutations and models to find what works best.

- **GUI for the whole team, library for engineers.** LangChain, LlamaIndex, DSPy, and Promptfoo are code-only. Kiln's desktop app lets PMs rate outputs, SMEs add training examples, and QA flag regressions — without a terminal. Engineers ship the same tasks via an MIT-licensed Python library.

- **Local-first.** LangSmith, W&B Weave, and most LLM-ops platforms are SaaS-only. Kiln runs entirely on your machine. Bring your own API keys, or go fully offline with Ollama. Your data never leaves your control.

- **190+ models tested across every provider.** OpenAI, Anthropic, Gemini, Bedrock, Ollama, OpenRouter, Fireworks, Groq, vLLM, llama.cpp, and any OpenAI-compatible endpoint. Swap models with confidence, not guesswork.

## Docs

Full docs at [docs.kiln.tech](https://docs.kiln.tech). Common starting points:

- [Quickstart](https://docs.kiln.tech/getting-started/quickstart) — run your first task in 5 minutes
- [Evals](https://docs.kiln.tech/docs/evaluations)
- [Auto-Optimize](https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer)
- [RAG](https://docs.kiln.tech/docs/documents-and-search-rag)
- [Agents](https://docs.kiln.tech/docs/agents)
- [Fine-Tuning](https://docs.kiln.tech/docs/fine-tuning-guide)
- [Python Library](https://docs.kiln.tech/developers/python-library-quickstart)
- [End-to-end project demo](https://docs.kiln.tech/docs/end-to-end-project-demo) (20-min video)

## Community

- Chat with the community on [Discord](https://kiln.tech/discord).
- Subscribe to the [newsletter](https://kiln.tech/blog) for new features.
- File issues, request features, or open a discussion on [GitHub](https://github.com/Kiln-AI/Kiln/issues).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.

## License

Kiln's core Python library and REST server are [MIT-licensed](libs/core/LICENSE.txt). The desktop app is [source-available](app), free to use, and free for personal use — built on the [fair-code](https://faircode.io) model so Kiln stays free for individuals while remaining sustainable.

Datasets are open JSON. You own and control your data; we never see it.

[Kiln Pro](https://kiln.tech/pricing) adds the AI Assistant, the Auto-Optimize runner, and auto-generated evals. Core Kiln remains fully functional without it.

**Trademarks:** The Kiln name and logos are trademarks of Chesterfield Laboratories Inc.

Copyright 2024 — Chesterfield Laboratories Inc.

## Citation

```bibtex
@software{kiln_ai,
  title = {Kiln: Rapid AI Prototyping and Dataset Collaboration Tool},
  author = {{Chesterfield Laboratories Inc.}},
  year = {2025},
  url = {https://github.com/Kiln-AI/Kiln},
  version = {latest}
}
```

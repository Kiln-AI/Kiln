---
name: kiln
description: Kiln is an app for building, evaluating and optimizing AI agents. Use when the user asks for /kiln or wants to work with Kiln.
---

# Kiln

Kiln is an app for building, evaluating and optimizing AI agents: prompts, models, tools, evals, synthetic data, fine-tuning and RAG. The user runs it on their own computer, and this skill connects you to it.

This build of Kiln has a placeholder skill. The full skill, with its guides, is not in this build yet. Until it is, tell the user that this version of Kiln cannot guide an agent yet, and suggest that they use the Kiln app directly at http://localhost:8757.

The API reference is in this build. To find an endpoint, start from `references/knowledge/api_docs/api_index.md`: it lists one catalogue per area of the API, and each catalogue names the doc of each endpoint by its file name. The endpoint docs are in `references/knowledge/api_docs/`: read one at `references/knowledge/api_docs/<file name>`, and read it before you call the endpoint with `call_kiln_api`.

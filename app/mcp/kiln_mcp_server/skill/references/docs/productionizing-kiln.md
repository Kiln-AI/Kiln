---
description: How to take ideas from the lab (Kiln) into your product
icon: industry-windows
---

# Productionizing Kiln

Kiln is a great place to rapidly experiment with many models, providers, fine-tunes, and prompts.&#x20;

Once you've found the ideal way to run your AI workload, you are ready to create (or iterate) on your product. This guide walks through the options for creating products from Kiln projects.

### Productionizing Kiln Tasks

#### Option 1: Use the Kiln Python Library

The MIT open-source [Kiln python library](https://docs.kiln.tech/developers/python-library-quickstart) powers all of the requests in the Kiln app. You can use it in your app or server, pointing it to the Kiln project of your choice.

Our python library docs have instructions for [exporting your project and running it via python](https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#run-a-kiln-task-from-python).

#### Option 2: Exporting Kiln Search Tools / RAG

We have multiple options for deploying search tools you build inside of Kiln. See the docs for options for [deploying search tools / RAG](references/docs/documents-and-search-rag.md#deploying-your-rag).

#### Option 3: \[Simple Tasks Only] Replicate Kiln Prompts and Requests in the Framework of your Choice&#x20;

{% hint style="warning" %}
This approach works well for simple single-turn AI tasks. However replicating a complete agent system with sub-agents, tools, or RAG can be quite challenging. We suggest using the Kiln library for complex tasks.
{% endhint %}

Every model request sent from Kiln is logged to `~/.kiln_ai/logs/model_calls.log` .  This includes the messages and any parameters sent to the API (model, temperature, reasoning, etc). It even includes a curl command to replicate the call Kiln made from the command line.

You can use the data in this log to exactly replicate any Kiln request in the language/framework of your choice. You can choose which tech-stack makes sense for your product; anything from simple HTTP requests, to integrating provider libraries (`pip install openai`), to integrating [llama.cpp](https://github.com/ggml-org/llama.cpp) into your app/process.&#x20;


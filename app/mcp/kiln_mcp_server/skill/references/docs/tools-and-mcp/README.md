---
description: Connect powerful tools to your Kiln tasks
icon: hammer
---

# Tools & MCP

Kiln allows connecting to tools such as [Kiln Search Tools (RAG)](references/docs/documents-and-search-rag.md) or third party tools via via [Model Context Protocol (MCP)](https://modelcontextprotocol.io). These tools can give your Kiln tasks powerful new capabilities.

## Video Walkthrough

{% embed url="https://www.youtube.com/watch?v=qh0FIrLMrII" %}

## Connecting Tools

First, connect some tools to your Kiln project. Tools are connected at the project level, and become available to all tasks in the project.

To connect a new set of tools, open "Tools" > "Add Tools".

### Quickstart: Math Tools

If you want to try tools as quickly as possible, enable the "Math Tools" from the "Add Tools" screen. These built into Kiln and don't require setting up a MCP server. They can be enabled in one click, and will add 4 simple math tools to your project: add, subtract, multiply and divide.

### Kiln Search Tools (RAG)

Kiln allows you to build powerful search tools, which can search thousands of documents for knowledge. These behave like any other tool: each search tool you create, will be automatically available in the tools dropdown.

See the [Documents & Search](references/docs/documents-and-search-rag.md) docs for details.&#x20;

### Powerful Example Tools: Web Search, Python Interpreter, and more

{% hint style="info" %}
The example MCP servers are not part of Kiln. You should trust the authors, their code, and their privacy policies before enabling them.
{% endhint %}

Kiln has several popular MCP servers pre-configured. You can get started with them in just a few clicks:

* [Web Search and Scrape by Firecrawl](https://docs.firecrawl.dev/mcp-server): Allows your task to search the web and scrape websites into text. Requires an API key from Firecrawl.
* [Run Python Code by Pydantic](https://ai.pydantic.dev/mcp/run-python/): Allows your model to generate then run python code. Powerful for allowing LLMs to perform tasks they normally don’t excel at: complex math, iterative computation, matrix math, etc. The python interpreter is sandboxed, and can’t access your system.
* [Local File Access by Anthropic](https://github.com/modelcontextprotocol/servers/tree/HEAD/src/filesystem): Allow your tasks to access files in specific folders on your local hard drive. You’ll be able to specify which folders it can access during setup.
* [Stock Quotes by Twelve Data](https://github.com/twelvedata/mcp): Realtime access to stock quotes and other market data. Requires a Twelve Data API key.
* [Control Github by Github](https://github.com/github/github-mcp-server): Manage repos, issues, PRs and workflows. Requires a GitHub Access Token.

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-04 at 1.47.57 PM (1).png" alt=""><figcaption><p>Example tools on the "Add Tools" screen</p></figcaption></figure>

You may need to install developer tools like Node.js or Deno before running these MCP servers. In each case, there’s a header at the top with a link to the appropriate dependency:

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-04 at 1.45.40 PM.png" alt="" width="375"><figcaption><p>Example dependency warning</p></figcaption></figure>

### Adding Custom MCP Servers

You can connect any MCP server to Kiln! MCP servers come in two flavours:

* Local servers: run locally on your computer, and are defined by a terminal command and arguments.
* Remote servers: run on a server and you connect to them over the web/http.

You can discover new MCP servers to use in registries like [MCP Pulse (external)](https://www.pulsemcp.com/servers).

#### Connecting Local MCP Servers

Once you’ve found a local MCP server you want to connect, click “Tools” > “Add Tools” > “Local MCP” > “Connect”, and provide the appropriate information in the setup:

* Name and Description: fields for you and your team to identify the server
* Command: The command to run. Just the actual command, not including arguments. For example: `npx`, `uvx`, `deno`, or similar. It should not include spaces.
* Arguments: any arguments to pass to the command, for example the `-y firecrawl-mcp` portion of the command `npx -y firecrawl-mcp`
* Environment variables: a list of environment variables. Be sure to specify which are secrets (like API keys), so that these aren't synced into your Kiln project on Git ([more info](references/docs/tools-and-mcp/#secret-management)).

{% hint style="info" %}
Be sure the server runs in [stdio mode](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#stdio). This is normally the default, but mode is sometimes is exposed as an argument.
{% endhint %}

<details>

<summary>Advanced Troubleshooting</summary>

Kiln will attempt to use your standard PATH to find the appropriate commands. If the command works in a fresh terminal window, they should work in Kiln. If you’re having issues:

1. Ensure the same command works in a new terminal window. If not, debug that by installing any missing dependencies, or adding the required commands to your PATH.
2. Ensure the server is running in [stdio mode](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#stdio), following its documentation.
3. If you need to specify a custom PATH variable for Kiln, you can set the custom\_mcp\_path variable in the YAML file \~/.kiln\_ai/settings.yaml to set PATH for all Kiln projects, or set PATH manually as an environment variable in a specific local MCP server config.

</details>

#### Connecting Remote MCP Servers

Once you’ve found a remote MCP server you want to connect, click "Tools” > “Add Tools” > “Remote MCP” > “Connect”, and provide the appropriate information in the setup:

* Name and Description: fields for you and your team to identify the server
* Server URL: The URL to the remote MCP server, for example https://api.githubcopilot.com/mcp/
* Headers: a list of headers to pass when calling the remote MCP server. Be sure to specify which are secrets (like API keys), so that these aren't synced into your Kiln project on Git ([more info](references/docs/tools-and-mcp/#secret-management)).

## Using Tools

Once you’ve connected tools, you can use them in any of your tasks. On the “Run” screen you can select which tools will be available to the model under “Advanced”. You can select any number of tools, then run your task as you normally would.

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-04 at 2.08.06 PM.png" alt="" width="182"><figcaption></figcaption></figure>

### Viewing Tool Calls

{% hint style="info" %}
The model may or may not choose to use the tools you provide. If you find the model is not using tools when you feel it should, update your prompt to more explicitly specify when tools should/must be used.
{% endhint %}

Tool calls happen behind the scenes, between the user message and the model's final output.

If you want to view which tools were called, their arguments, and their results look at the "All Messages" section on the "Run" screen or when viewing a dataset entry. You'll be able to see tool calls the model makes, as well as the tool's response:

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-22 at 11.49.42 AM.png" alt="A Trace Including Tool Calls" width="375"><figcaption><p>A Trace Showing a Tool Call</p></figcaption></figure>

## Guidance / Understanding Tools

### Always Select Models Optimized for Tool Calling

Not all models are designed with tools in mind. Calling tools requires precise syntax and models that were not trained for tool-calling often fail. This makes it important to select a model with tool support.

Kiln tests every model for its capabilities to minimize guesswork; you can read more about our testing methodology [here](https://kiln.tech/blog/i_wrote_2000_llm_test_cases_so_you_dont_have_to). You can view our [model library](https://app.gitbook.com/u/lbKlVk0pqscWejhogcdq9NRaUtP2) and filter to Capability=Tools to see which models and providers we suggest for tool calling.

When you select a model in Kiln, you’ll see a warning if tools are not supported. While you can still try these models, they are likely to fail:

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-05 at 2.24.36 PM.png" alt="" width="375"><figcaption><p>Ignore the warnings at your peril</p></figcaption></figure>

### Don’t Add Too Many Tools

When you add tools to a task run, the model processes their names and descriptions as part of its context. Adding a few relevant tools can be a great way to improve task performance, but if you add dozens or hundreds you’ll both fill your context and dilute the model’s attention. The right number will depend on your task and the base model, but be selective when adding tools.

See our [video guide at 7m23s](https://youtu.be/qh0FIrLMrII?si=CHiJ1CCen_2MA5A3\&t=443) for a discussion of these concepts:

<figure><img src="../../.gitbook/assets/Context-2.png" alt=""><figcaption></figcaption></figure>

### Synthetic Data & Fine-Tuning with Tools

At this time, Kiln doesn’t support tool calling for synthetic data and fine-tuning. Rest assured, we’re working on adding it!

### Secret Management

Often MCP servers require secrets, like API keys. However, Kiln projects are designed to be [shared across teams with Git](references/docs/collaboration/) and you don’t want to commit secrets in a Git repo.

To address this, Kiln allows you to mark headers and environment variables as secrets. Secrets are never stored in the Kiln project files, which are designed to be shared/synced. If a team member adds a tool which requires secrets, anyone who syncs it will have to re-enter the secrets in settings before using the tool. Non-secret headers and environment variables will be synced automatically.

<figure><img src="../../.gitbook/assets/Screenshot 2025-09-05 at 3.42.28 PM.png" alt="" width="375"><figcaption><p>Identify secrets on tool setup</p></figcaption></figure>

## Kiln MCP Server

The documentation above is for using Kiln as a MCP client (where Kiln calls other MCP servers to use tools). Kiln can also function as a MCP server (where Kiln exposes tools to other MCP clients).&#x20;

Kiln can expose tools for:

* Any [Search Tools (RAG)](references/docs/documents-and-search-rag.md) you have created in Kiln
* Any [Kiln Task as Tool](references/docs/agents.md#multi-actor-interaction-aka-subtasks) agents you have created in Kiln

To use Kiln as a tool server

* Install Kiln CLI server tools: `uv tool install kiln_server`&#x20;
* Run the `kiln_mcp` command, pointing it to the Kiln project you want to host. See [the docs on the Kiln MCP Server](https://github.com/Kiln-AI/Kiln/tree/main/libs/server/kiln_server/mcp#readme) for details.

---
status: complete
---

# Kiln Environments

Add support in Kiln for using synthetic worlds on the run page, and for hitting real tools such as staging (generic for any SaaS). The current data model needs changing: the same run config should be able to point at a synthetic world or at a real tool.

## Scope decision (2026-11-09)

V1 is running a synthetic world on the run page. A world gets a list of named reset kwargs, each a name and the kwargs for the world's `reset`, such as "Acme Manager" (`{fixture: acme, role: mgr}`) and "Acme Tech" (`{fixture: acme, role: tech}`). The run page shows them in a dropdown when the run config uses a world.

Later the same day: worlds are renamed to environments in code and files, the UI calls them "OpenEnv", and the dropdown is "Environment Options". The V2 object that swaps real and synthetic tools needs a new name.

Swapping sources such as synthetic, staging and prod, described below, is V2.

Open items from the original notes:

- Run should work against staging and against a synthetic world.
- Auto optimize makes code tools and does not edit the world, so the data model needs rethinking.
- The winning run config should be the one that runs, with a switch choosing the environment.
- Should Eval Builder V2 be able to generate synthetic data tied to a world?

## Concept

- Real companies have many environments: prod, staging, dev, one-off deployments.
- We add OpenEnv environments as another environment type.
- A run config is a model, prompt and set of tools, but we should be able to run the same run config against multiple environments.
- Environment APIs are fairly hard to change in real life.
  - The same tool definition exists in every environment by design.
  - We optimize by writing code tools calling into environment tools, not by assuming we can just change the environment.
  - Why:
    - Sometimes you can't change the tool (e.g. Stripe APIs, external APIs). Assuming we can optimize "env tools" is a mistake.
    - Even if it's not a firm "can't", changing real enterprise tools is expensive: schedule a meeting, a weekly sync, get it resourced, get dependencies to migrate. It can take months.
- This leads to two tiers of tools:
  - Env tools: fairly static. Can call out to databases, can do anything. Hard to change in real life, so good to be static in Kiln.
  - Kiln code tools / wrapper tools: can only call other tools (env and code). Easy to version and change, as their only dependency is other tool definitions. Not a good idea to call out to a DB etc. (we won't block it, but it's not ideal). Kiln code tools can't add dependencies, so it's better if DB calls etc. are env tools anyway.

## Kiln Environments

### UI

- A new toggle on the run page: "Staging", "Prod", "Synthetic (large co, admin)", "Synthetic (large co, technician)", "Synthetic (small co, owner)".
- A way to set up and manage environments in settings.

### What an environment does: it's a tool mapping

Run configs contain standard tool names/IDs:

- Something like `call_acme_rest_api`.
- Not `synthetic_world::123::tool::456::call_acme_rest_api`.

Environments are essentially a map of base tool name to a concrete tool:

- "Synthetic (large co, admin)"
  - `call_acme_rest_api` -> `synthetic_world::123::tool::456::call_acme_rest_api`
- "Staging"
  - `call_acme_rest_api` -> `remote_mcp::1234::tool::call_acme_rest_api`

For example:

```json
{
  "tool_a": "synthetic_world::234::tool_a",
  "tool_b": "remote_mcp::4564::tool_b"
}
```

That way we can still build an environment that is a mix of real and fake:

- Database calls all point to a synthetic world.
- A `web_search` tool points at the real web search tool over MCP. We're not creating a "synthetic internet".

When creating an environment, we need to check every tool mapping:

- Example: `call_acme_rest_api` can't map to `web_search`.
- Check the signatures are compatible when creating an environment:
  - Check the tool call params are compatible (can be a subset in one direction, but can't be missing).
  - Name and description don't need to match, but we need to be careful which we expose to the agent. We should expose the name and description from the base tool, not the mapped one. The model sees these, so changing them is changing the run config itself.
  - P2: a parameter mapping option in the environment mapping: a `start` param in the tool call passed to the `offset` param of the env tool.

### What is the environment data model?

Probably a new Kiln datamodel. Actually somewhat simple:

- name
- description
- set of tool mappings

Note: it doesn't say how to connect the tools. We already have several ways to add tools:

- Remote MCP
- Local MCP
- Synthetic worlds

So we don't reinvent any of that. It's really just a mapping of tools: "When you call `tool_x`, proxy that call to `remote_mcp::3464356::tool_x`".

### The base tools

- If they connect an MCP server, its tools just appear.

### How eval inputs set an environment

TBD whether you need to create an environment object for each and refer to it by ID, or inline it.

---
status: complete
---

# UI Design: OpenEnv Environments on the Run Page

Every screen reuses an existing Kiln pattern. OpenEnv environments are managed next to MCP servers, and their screens copy the tool server screens. The run page gains one dropdown.

The UI calls the thing "OpenEnv", the way MCP servers are shown as "MCP Server". It calls a named reset kwargs entry an **Environment Option**, and the kwargs themselves **Reset Arguments**: "kwargs" is Python jargon, and Kiln's labels use plain, full words. The data model keeps `reset_kwargs`, the way MCP tools show "Arguments" for a schema's `parameters`. In code these are `OpenEnvServer` and `named_reset_kwargs` (see the functional spec's Naming section).

## Page inventory

| Page | Route | Copies |
|---|---|---|
| Tools list (existing) | `tools/[project_id]` | Gains OpenEnv rows |
| Add Tools (existing) | `tools/[project_id]/add_tools` | Gains an "OpenEnv" item |
| Connect OpenEnv | `tools/[project_id]/add_tools/openenv` | Remote MCP connect form |
| OpenEnv detail | `tools/[project_id]/openenv_servers/[openenv_server_id]` | Tool server detail page |
| Edit OpenEnv dialog | Overlay on OpenEnv detail | `edit_dialog.svelte` |
| Environment Option dialog | Overlay on OpenEnv detail | `dialog.svelte` with a form |
| Run page (existing) | `run` | Gains the Environment Options dropdown |
| Conversation page (existing) | `dataset/[project_id]/[task_id]/[run_id]/run` | Shows the OpenEnv and its reset arguments |

Breadcrumbs follow the tools pages: Optimize > Tools > [name].

## Tools list

OpenEnv rows sit in the existing tools table with the other tool servers.

- **Name:** the environment's name.
- **Type:** "OpenEnv". The Type column names how Kiln connects, like "Remote MCP", not what the server contains.
- **Description:** the environment's description.
- **Status:** "Ready", in the same `Warning` style as MCP servers.

Clicking a row opens the OpenEnv detail page.

## Add Tools

The "Custom Tools" `KilnSection` gains an item:

- **Name:** "OpenEnv".
- **Description:** "Connect an OpenEnv server, such as a copy of your product that agents can act in safely. Learn more", where "Learn more" links to the OpenEnv docs page (to be written; https://docs.kiln.tech/docs/tools-and-mcp until then). `settings_item.svelte` renders descriptions as plain text today, so it needs an optional link.
- **Button:** "Connect".

## Connect OpenEnv and Edit OpenEnv

Connect OpenEnv is a page with a `FormContainer` (`submit_label="Connect"`) inside `max-w-4xl`. AppPage keeps its "Read the Docs" link. At the top of the body, above the form, Kiln's `Callout` (`lib/ui/callout.svelte`, the same component as "Update Available" on Settings) promotes Kiln Seahaven: a "build" icon (a line-style wrench SVG) in its normal round icon bubble, the title "Build an OpenEnv with Kiln Seahaven", a one-line description, and its built-in button, "Learn More" (`btn-primary btn-sm`), linking to https://github.com/Kiln-AI/Seahaven. The button sits on the right and drops below the text on narrow screens. No change to `Callout` or `CalloutCard` is needed.

UI copy avoids "synthetic" and "mock". It says "copy of your product" where it needs to describe what most OpenEnv servers are.

Edit OpenEnv is `edit_dialog.svelte`, opened by the Edit button on the detail page, with the same three fields and Save.

- **Name:** a text input.
- **Description:** a textarea, optional.
- **Server URL:** placeholder `http://127.0.0.1:8004`. Its `info_description` says Kiln connects to this server and never starts it. It stays editable, because a local server's port can change.

Saving goes to the detail page. Environment Options aren't on this form. They're added from the detail page, after Kiln can show the environment's tools.

## OpenEnv detail

AppPage: title "OpenEnv", subtitle "Name: Acme". Action buttons:

- **Edit**
- No Delete button in V1.

Row 1, two columns of `PropertyList`, laid out like the tool server page:

- **Properties:** Name, Description, Type ("OpenEnv").
- **Connection Details:** Server URL, Version (the `name@version` the server reports, or the error if it's offline).

Row 2, **Environment Options**:

- A header copied from Run Configurations on the Optimize page (`optimize/[project_id]/[task_id]/+page.svelte`): an `h2 text-lg font-medium` title "Environment Options" with a `text-sm text-gray-500` subtitle under it, and an "Add Environment Option" `btn btn-mid` on the right, centred across both lines. It wraps under the title when there isn't room. The table sits `gap-4` below.
- The subtitle: "The reset options sent to the OpenEnv, saved under a name, such as which company's data to load and which user the agent acts as. Pick one from Environment Options on the run page."
- A bordered table with columns Name, Reset Arguments and a `TableActionMenu` (Edit, Clone, Remove). Clone opens Add Environment Option prefilled with the same kwargs and the name "[name] (copy)", as Clone does for code tools; nothing is saved until Save. Reset Arguments shows the JSON formatted over several lines (2-space indent) in `font-mono text-sm`.
- With no Environment Options, the table frame holds the message, like Saved Prompts on the Prompts page (`text-gray-500 rounded-lg border p-4 text-sm`): "No Environment Options yet. Add one by clicking "Add Environment Option" above." The Add button stays.
- Rows are listed in the order they were added. The first is the run page default.

Row 3, **Available Tools**: the same table as a tool server's: Name, Description, Arguments. If the server is offline, a full-width `ErrorDetailsBlock` titled "Can't Reach OpenEnv" replaces the table. The component is fixed at a centred 600px today, so it needs a full-width option for use inside a section. Its troubleshooting steps: check the server is running, and check the Server URL. Environment Options stay editable while it's offline.

## Environment Option dialog

`dialog.svelte`, titled "Add Environment Option" or "Edit Environment Option", containing a `FormContainer` with `submit_label="Save"`.

- **Name:** a text input, e.g. "Acme Tech". It must be unique within the environment.
- **Reset Arguments:** the code editor in JSON mode, `min_height="160px"`. Its description: "Passed to the OpenEnv's reset(). Which keys exist depends on the server." Invalid JSON, or JSON that isn't an object, shows the form's inline error and blocks Save. An empty object is allowed.

The code editor only loads Python today, so this adds the `@codemirror/lang-json` dependency.

We considered a Name/Value row editor (`FormList`, as for MCP headers) with an "Edit as JSON" toggle, and decided against it for V1. Reset arguments are free-form and often nested, and the OpenEnv server publishes no schema to build a form from.

Remove takes effect right away, with no confirmation. An Environment Option is only a named shortcut for some kwargs, and past runs keep the kwargs they used.

## Tool picker

The existing `tools_selector.svelte` multi-select, fed by `available_tools`. OpenEnv tools need no new control.

- Each environment is its own option group after the MCP server groups, labelled "OpenEnv: Acme", like "MCP Server: Docs Search".
- An offline environment is hidden from the picker, the same as an MCP server that can't be reached (`available_tools` skips it). Tools already selected from it stay selected: `drop_unselectable_tools` in `tools_selector.svelte` must not drop `kiln_tool::openenv::` ids. Run then fails with the can't-reach error. The environment's page shows why.
- Nothing is disabled. Selecting tools from two environments is allowed in the picker; the Environment Options field and Run report it.

## Run page

The Options sidebar keeps its order, with one control added after Skills and before Advanced Options:

1. Run Configuration
2. Model
3. Prompt Method
4. Tools & Search
5. Skills
6. **Environment Options** (new)
7. Advanced Options (`collapse.svelte`)

Environment Options:

- A `FormElement` with `inputType="fancy_select"` and `label="Environment Options"`.
- `info_description`: "Sets the OpenEnv's starting data for this run, such as the company and the user the agent acts as."
- Hidden unless the selected run config, saved or unsaved, can reach an OpenEnv tool. It appears and disappears as tools change.
- Options are the environment's Environment Options in the order they were added. Each option's description is its reset arguments as formatted JSON. `fancy_select` descriptions are clamped to three lines and collapse indentation today, so it needs a mode that shows preformatted text in full. The first is selected.
- With no Environment Options, the empty state reads "No Environment Options" with an "Add Environment Options" link to the detail page, like the tool picker's empty state. The run then resets with no kwargs.
- If the selected tools reach more than one environment, the dropdown is replaced by an error line in the field's error style: "Your tools use more than one OpenEnv (Acme, Beta). A run can only use one." Clicking Run returns the same error.
- It isn't inside Advanced Options, because a run with an environment can't start without it.
- It isn't part of the run config, so saving a run config doesn't save it.

The choice isn't remembered across page loads.

## Multi-turn

Before the first message, the run page shows the dropdown as above. After the first turn, Kiln moves to the conversation page as it does today.

On the conversation page:

- The sidebar shows the OpenEnv and the Reset Arguments the session started with, as read-only properties, with the JSON formatted over several lines. It shows the arguments, not the option's name, because options can be renamed or removed later.
- If the session has ended, sending a message shows an error `Warning` above the composer: "The OpenEnv session for this conversation ended. Start a new conversation to keep using this OpenEnv." The conversation stays readable.
- Forking from an earlier turn is disabled in a conversation with an environment. The Fork action's tooltip says why: "This conversation uses an OpenEnv, so it can only continue from the latest turn."

## Run output

The run sidebar has Rating and Feedback, Tags and Usage today, with no general property list. When a run has an environment, a `PropertyList` titled "OpenEnv" is added after Usage, with OpenEnv and Reset Arguments (from `openenv_episode`). Raw Data already includes `openenv_episode`, with the kwargs and final state.

## Errors

The messages come from the functional spec: more than one environment, environment unreachable or at capacity, and reset kwargs rejected. All three happen before the model is called, so they're request errors and show as the form's error line above Run, not the "Run Failed" trace view. That view is only for failures inside the run. This assumes the session is reset before the adapter is invoked, as the eval runner does.

## Responsive behavior

No new layouts. Every page inherits its pattern's responsive behavior: the run page's sidebar stacks below the input under `xl`, and the detail page's two property columns stack under `lg`.

## Copy

New strings not already given above. The mockups' "All copy" section lists every string on every screen, marked existing, from this spec, or proposed.

| Where | Text |
|---|---|
| Connect OpenEnv subtitle | Connect to a running OpenEnv server to add its tools to your project. |
| Read the Docs and Learn more links | https://docs.kiln.tech/docs/tools-and-mcp, until an OpenEnv docs page exists |
| Kiln Seahaven callout title | Build an OpenEnv with Kiln Seahaven |
| Kiln Seahaven callout description | Kiln Seahaven is an open-source framework for building realistic copies of your product's tools and data, served as an OpenEnv. |
| Kiln Seahaven callout button | Learn More |
| Name field description | A name to identify this OpenEnv. |
| Description field description | A description of this OpenEnv for your reference. |
| Server URL field description | The URL of the OpenEnv server. |
| Server URL info tooltip | Kiln connects to this server but never starts or stops it. Start the server before you connect. |
| Server URL error | Enter a full URL starting with http:// or https://, like http://127.0.0.1:8004. Replaces the backend's developer message ("env_url must be an http:// or https:// URL with a host"). |
| Version, offline | Can't reach OpenEnv: connection refused |
| Offline troubleshooting steps | Check the OpenEnv server is running. / Check the Server URL. |
| Reset Arguments errors | Reset arguments must be valid JSON. / Reset arguments must be a JSON object. |
| Duplicate option name | An Environment Option named [name] already exists. |
| Run error, unreachable | Can't reach OpenEnv [name] at [url]. Check the server is running. |
| Run error, reset rejected | [name] rejected the reset arguments: [server's message] |
| Run error, at capacity | OpenEnv [name] is at capacity. Wait for a run to finish, or raise the server's session limit. |
| OpenEnv property on runs | Links to the OpenEnv detail page. |

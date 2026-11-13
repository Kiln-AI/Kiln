---
status: complete
---

# UI Design: OpenEnv Environments on the Run Page

Every screen reuses an existing Kiln pattern. OpenEnv environments are managed next to MCP servers, and their screens copy the tool server screens. The run page gains one dropdown.

The UI calls the saved record an **OpenEnv Server**, the way MCP's is "MCP Server", matching the code's `OpenEnvServer`. "OpenEnv" alone means only the framework or protocol. The UI calls a named reset kwargs entry an **Environment Preset**, and the kwargs themselves **Reset Arguments**: "kwargs" is Python jargon, and Kiln's labels use plain, full words. "Preset" is the standard word for a named, saved set of settings; "option" was vague, since each one is itself a set of reset options. No other Kiln screen uses "preset", so the word is free. The data model keeps `reset_kwargs` and `named_reset_kwargs`, the way MCP tools show "Arguments" for a schema's `parameters` (see the functional spec's Naming section).

## Page inventory

| Page | Route | Copies |
|---|---|---|
| Tools list (existing) | `tools/[project_id]` | Gains OpenEnv Server rows |
| Add Tools (existing) | `tools/[project_id]/add_tools` | Gains an "OpenEnv Servers" item |
| Connect OpenEnv Server | `tools/[project_id]/add_tools/openenv` | Remote MCP connect form |
| OpenEnv Server detail | `tools/[project_id]/openenv_servers/[openenv_server_id]` | Tool server detail page |
| Edit OpenEnv Server dialog | Overlay on the detail page | `edit_dialog.svelte` |
| Environment Preset dialog | Overlay on the detail page | `dialog.svelte` with a form |
| Run page (existing) | `run` | Gains the Environment Preset dropdown, in Advanced Options |
| Conversation page (existing) | `dataset/[project_id]/[task_id]/[run_id]/run` | Shows the OpenEnv Server and its reset arguments |

Breadcrumbs follow the tools pages: Optimize > Tools > [name].

## Tools list

OpenEnv Server rows sit in the existing tools table with the other tool servers.

- **Name:** the server's name.
- **Type:** "OpenEnv Server", like "Remote MCP" names how Kiln connects.
- **Description:** the server's description.
- **Status:** "Ready", or "Archived" for an archived server, in the same `Warning` styles as MCP servers. Archived servers are listed after the others.

Clicking a row opens the detail page.

## Add Tools

The "Custom Tools" `KilnSection` gains an item, worded like the two MCP items:

- **Name:** "OpenEnv Servers", plural like "Remote MCP Servers".
- **Description:** "Connect to OpenEnv servers to add tools to your project."
- **Link:** "Learn more", on its own line under the description, linking to the OpenEnv docs page (to be written; https://docs.kiln.tech/docs/tools-and-mcp until then). `settings_item.svelte` gains an optional link for this.
- **Button:** "Connect".

## Connect OpenEnv Server and Edit OpenEnv Server

Connect OpenEnv Server is a page with a `FormContainer` (`submit_label="Connect"`) inside `max-w-4xl`. AppPage keeps its "Read the Docs" link. At the top of the body, above the form, Kiln's `Callout` (`lib/ui/callout.svelte`, the same component as "Update Available" on Settings, so its icon circle is the same size) promotes Kiln Seahaven: a buildings icon (`buildings_icon.svelte`, an outline drawing of a tall tower between two shorter buildings on a ground line, centred in its 24×24 box) in its normal round icon bubble, the title "Build an OpenEnv Server with Kiln Seahaven", a one-line description, and its built-in button, "Learn More" (`btn-primary btn-sm`), linking to https://github.com/Kiln-AI/Seahaven. The button sits on the right and drops below the text on narrow screens. No change to `Callout` or `CalloutCard` is needed.

UI copy avoids "synthetic" and "mock". It says "copy of your product" where it needs to describe what most OpenEnv servers are.

The fields copy the MCP server connect form's label, description and placeholder, with "MCP" replaced by "OpenEnv":

- **Name:** a text input. "A name to identify this OpenEnv server."
- **Description:** a textarea, optional. "A description of this OpenEnv server for your reference."
- **Server URL:** "The URL of the OpenEnv server.", placeholder `https://example.com/openenv`. No info tooltip, since the MCP form has none. It stays editable, because a local server's port can change.

Connect checks the server answers at its URL before saving, as MCP connect does. If it doesn't, nothing is saved and the form shows an `ErrorDetailsBlock` titled "Could Not Connect to OpenEnv Server" above the Connect button, with MCP's troubleshooting steps (verify the URL, verify the server is running, check your network, check Kiln logs).

Edit OpenEnv Server is `edit_dialog.svelte`, opened by the Edit button on the detail page, with the same three fields and Save. Changing the URL runs the same check, and the dialog shows the error. Changing only the name or description doesn't contact the server.

Saving goes to the detail page. Environment Presets aren't on this form. They're added from the detail page, after Kiln can show the server's tools.

## OpenEnv Server detail

AppPage: title "OpenEnv Server", subtitle "Name: Acme". Action buttons, as on an MCP server's page:

- **Edit**
- **Archive**, or **Unarchive** for an archived server. An archived server shows MCP's warning: "This OpenEnv server is archived. You may unarchive it to use it again."
- No Delete button in V1. Archive also covers a mistyped URL that was saved.

Row 1, two columns of `PropertyList`, in the order and format of the MCP server page:

- **Properties:** ID, Name, Description, Created At, Created By.
- **Connection Details:** Type ("OpenEnv Server"), Server URL, Version (the `name@version` the server reports, or "Can't reach OpenEnv server" if it's offline).

Row 2, **Environment Presets**:

- A header copied from Run Configurations on the Optimize page (`optimize/[project_id]/[task_id]/+page.svelte`): an `h2 text-lg font-medium` title "Environment Presets" with a `text-sm text-gray-500` subtitle under it, and an "Add Environment Preset" `btn btn-mid` on the right, centred across both lines. It wraps under the title when there isn't room. The table sits `gap-4` below.
- The subtitle: "Named sets of reset arguments for the OpenEnv server, such as which company's data to load and which user the agent acts as. Pick one under Advanced Options on the run page."
- A bordered table with columns Name, Description, Reset Arguments and a `TableActionMenu` (Edit, Clone, Remove). Clone opens Add Environment Preset prefilled with the same description and kwargs and the name "[name] (copy)", as Clone does for code tools; nothing is saved until Save.
- Description and Reset Arguments each show one truncated line: the description as text ("None" when empty), the arguments as compact JSON in `font-mono text-sm`. Clicking a row expands it to the full description and the JSON formatted over several lines (2-space indent). This is the synthetic data tables' truncate-and-expand pattern (`generated_data_node.svelte`, `kiln_pro_inputs.svelte`): a clickable row, `truncate w-0 min-w-full` when collapsed, `whitespace-pre-wrap break-words` when expanded, and an actions cell that doesn't toggle the row.
- With no Environment Presets, the table frame holds the message, like Saved Prompts on the Prompts page (`text-gray-500 rounded-lg border p-4 text-sm`): "No Environment Presets yet. Add one by clicking "Add Environment Preset" above." The Add button stays.
- Rows are listed in the order they were added. The first is the run page default.

Row 3, **Available Tools**: the same table as a tool server's: Name, Description, Arguments. If the server is offline, a full-width `ErrorDetailsBlock` titled "Can't Reach OpenEnv Server" replaces the table. The component is fixed at a centred 600px today, so it needs a full-width option for use inside a section. Its troubleshooting steps: check the server is running, and check the Server URL. Environment Presets stay editable while it's offline.

## Environment Preset dialog

`dialog.svelte`, titled "Add Environment Preset" or "Edit Environment Preset", containing a `FormContainer` with `submit_label="Save"`.

- **Name:** a text input, placeholder "Name", description "Shown in the Environment Preset dropdown on the run page.", and an info tooltip with examples: For example, "Small Startup" or "Large Company, Admin User". It must be unique within the server.
- **Description:** a textarea, optional. "Shown under the name in the Environment Preset dropdown."
- **Reset Arguments:** a section below the two fields, headed by a `SettingsHeader` (the section header Kiln uses inside forms and dialogs, e.g. `claim_trace_modal.svelte`) so it reads a level above its fields. Its subtitle: "Passed to the OpenEnv server's reset(). Which keys exist depends on the server." Under it, the code editor in JSON mode, `min_height="160px"`. Invalid JSON, or JSON that isn't an object, shows the form's inline error and blocks Save. An empty object is allowed.

The code editor only loads Python today, so this adds the `@codemirror/lang-json` dependency.

We considered a Name/Value row editor (`FormList`, as for MCP headers) with an "Edit as JSON" toggle, and decided against it for V1: reset arguments are free-form and often nested. A form built from a schema the server publishes is different, and is added below.

### Reset Arguments from a schema (phase 8)

When the OpenEnv server publishes a reset schema (functional spec, Reset argument forms), Reset Arguments becomes a form:

- The section keeps its "Reset Arguments" header, with a "Raw JSON" link in the header's actions, on the title's row. The form shows by default.
- The form is the existing schema form from the run page (`run_input_form.svelte`, which builds `run_input_form_element` fields), so fields look and behave like structured task inputs: a dropdown for enums, a number input, a text input, a nested group for an object. Each field has the schema's title and description and an "optional" marker unless required. An optional enum's dropdown starts on "Not Set", listed first; a required enum asks "Select an option".
- Raw JSON shows the JSON editor with the form's current value, and the link becomes "Form". "Form" reads the JSON back into the form. If the JSON is invalid, or has keys or values the form can't show, the editor stays and the form's inline error says why.
- While the schema loads, the dialog shows the JSON editor, so a slow or offline server never blocks editing. A schema that arrives after the user has typed in the editor doesn't switch the view.
- Edit and Clone open on the form when the preset's arguments fit it, and on Raw JSON otherwise.
- With no schema, there is no link, and the dialog is exactly the JSON editor described above.

Enum fields use Kiln's dropdown, not the chip buttons in Seahaven's console, so the dialog matches the rest of Kiln.

Remove takes effect right away, with no confirmation. An Environment Preset is only a named shortcut for some kwargs, and past runs keep the kwargs they used.

## Tool picker

The existing `tools_selector.svelte` multi-select, fed by `available_tools`. OpenEnv tools need no new control.

- Each server is its own option group after the MCP server groups, labelled "OpenEnv Server: Acme", like "MCP Server: Docs Search".
- An offline server is hidden from the picker, the same as an MCP server that can't be reached (`available_tools` skips it). Tools already selected from it stay selected: `drop_unselectable_tools` in `tools_selector.svelte` keeps `kiln_tool::openenv::` ids whose server isn't archived. Run then fails with the can't-reach error. The server's page shows why.
- An archived server behaves as an archived MCP server: `available_tools` leaves it out, and the picker drops its tools from the selection. To tell archived from offline, the picker reads the project's OpenEnv servers once a selected tool is an OpenEnv one.
- Nothing is disabled. Selecting tools from two servers is allowed in the picker; the Environment Preset field and Run report it.

## Run page

The Options sidebar keeps its order. The new field goes at the bottom of Advanced Options, which starts collapsed:

1. Run Configuration
2. Model
3. Prompt Method
4. Tools & Search
5. Skills
6. Advanced Options (`collapse.svelte`), ending with **Environment Preset** (new)

The field appears only after the tools lookup answers. Outside the collapse it popped in and shifted the layout, so it sits inside it.

Environment Preset:

- A `FormElement` with `inputType="fancy_select"` and `label="Environment Preset"`.
- `info_description`: "Sets the OpenEnv server's starting data for this run, such as the company and the user the agent acts as."
- Hidden unless the selected run config, saved or unsaved, can reach an OpenEnv tool. It appears and disappears as tools change.
- Options are the server's Environment Presets in the order they were added. Each option's description line is the preset's description, as plain text; a preset with no description shows only its name. No JSON is shown. The first is selected.
- With no Environment Presets, the empty state reads "No Environment Presets" with an "Add Environment Preset" link to the detail page, like the tool picker's empty state. The run then resets with no kwargs.
- If the selected tools reach more than one server, the dropdown is replaced by an error line in the field's error style: "Your tools use more than one OpenEnv server (Acme, Beta). A run can only use one." Clicking Run returns the same error, so a hidden field can't let a bad run through.
- It isn't part of the run config, so saving a run config doesn't save it.

The choice isn't remembered across page loads.

## Multi-turn

Before the first message, the run page shows the dropdown as above. After the first turn, Kiln moves to the conversation page as it does today.

On the conversation page:

- The sidebar shows the OpenEnv Server and the Reset Arguments the session started with, as read-only properties, with the JSON formatted over several lines. It shows the arguments, not the preset's name, because presets can be renamed or removed later.
- If the session has ended, sending a message shows an error `Warning` above the composer: "The OpenEnv session for this conversation ended. Start a new conversation to keep using this OpenEnv server." The conversation stays readable.
- Forking from an earlier turn is disabled in a conversation with a server. The Fork action's tooltip says why: "This conversation uses an OpenEnv server, so it can only continue from the latest turn."

## Run output

The run sidebar has Rating and Feedback, Tags and Usage today, with no general property list. When a run has an environment, a `PropertyList` titled "OpenEnv" is added after Usage, with OpenEnv Server, Version (`openenv_episode.openenv_version`, the `name@version` the server reported when the run started) and Reset Arguments. The Version row says which server version the run ran against; pinning a version is out of scope. Raw Data already includes `openenv_episode`, with the kwargs and final state.

## Errors

The messages come from the functional spec: more than one server, server unreachable or at capacity, and reset kwargs rejected. All three happen before the model is called, so they're request errors and show as the form's error line above Run, not the "Run Failed" trace view. That view is only for failures inside the run. This assumes the session is reset before the adapter is invoked, as the eval runner does.

## Responsive behavior

No new layouts. Every page inherits its pattern's responsive behavior: the run page's sidebar stacks below the input under `xl`, and the detail page's two property columns stack under `lg`.

## Copy

New strings not already given above. The mockups' "All copy" section lists every string on every screen, marked existing, from this spec, or proposed.

| Where | Text |
|---|---|
| Connect OpenEnv Server subtitle | Connect to a running OpenEnv server to add its tools to your project. |
| Read the Docs and Learn more links | https://docs.kiln.tech/docs/tools-and-mcp, until an OpenEnv docs page exists |
| Kiln Seahaven callout title | Build an OpenEnv Server with Kiln Seahaven |
| Kiln Seahaven callout description | Kiln Seahaven is an open-source framework for building realistic copies of your product's tools and data, served as an OpenEnv server. |
| Kiln Seahaven callout button | Learn More |
| Name field description | A name to identify this OpenEnv server. |
| Description field description | A description of this OpenEnv server for your reference. |
| Server URL field description | The URL of the OpenEnv server. |
| Server URL placeholder | https://example.com/openenv |
| Server URL error | Enter a full URL starting with http:// or https://, like http://127.0.0.1:8004. Replaces the backend's developer message ("env_url must be an http:// or https:// URL with a host"). |
| Server not answering on Connect or Edit | The session manager's message, e.g. "OpenEnv server 'Acme' points at [url], which did not answer /metadata: [reason]" |
| Version, offline | Can't reach OpenEnv server |
| Offline troubleshooting steps | Check the OpenEnv server is running. / Check the Server URL. |
| Archived warning | This OpenEnv server is archived. You may unarchive it to use it again. |
| Reset Arguments errors | Reset arguments must be valid JSON. / Reset arguments must be a JSON object. |
| Raw JSON link | Raw JSON / Form |
| Reset Arguments description, with a schema | From the OpenEnv server's reset schema. Leave a field empty to use the server's default. |
| Raw JSON can't switch back | The form can't show these reset arguments: [what doesn't fit, e.g. "unknown field 'foo'"]. Edit them as JSON. |
| Duplicate preset name | An Environment Preset named [name] already exists. |
| Run error, unreachable | Can't reach OpenEnv server [name] at [url]. Check the server is running. |
| Run error, reset rejected | [name] rejected the reset arguments: [server's message] |
| Run error, at capacity | OpenEnv server [name] is at capacity. Wait for a run to finish, or raise the server's session limit. |
| OpenEnv Server property on runs | Links to the OpenEnv Server detail page. |

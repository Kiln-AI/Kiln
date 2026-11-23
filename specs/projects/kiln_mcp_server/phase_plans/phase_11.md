---
status: complete
---

# Phase 11: The Connect page, the install guide, the README section and the `kiln_mcp` rename

## Overview

How a user gets from the Kiln app, the README or the docs to an agent with the Kiln MCP server and the stub skill ([connect_page_and_install](../components/connect_page_and_install.md); [ui_design](../ui_design.md)). The web UI gains a callout on Settings and the page `/settings/connect_agent`, which shows the one install prompt and the MCP server URL, each with a Copy button. The repo gains `agent_install.md` (the guide the prompt points at, holding the only copy of the stub skill) and a README section with the same prompt. The existing `kiln_mcp` command's docs and `--help` text are renamed to "Kiln project tools MCP server", so the two MCP servers are not confused. No endpoint is added or changed, so no schema, annotation or API reference file changes.

The UI work follows the `kiln-ui` skill: the component plan is section 3.1 of the component doc (it is not committed into the app); no shared control under `lib/` changes; the gate must report 0 FAIL, 0 WARN on the route files.

## Steps

1. **Settings callout.** `app/web_ui/src/routes/(app)/settings/+page.svelte`: add an `{:else}` to the update callout's `{#if}` with a `Callout` (`testid="connect-agent-callout"`, title "Connect Kiln to Claude, Codex, OpenCode and more", description "Use Kiln from your own coding agent.", `button_label="Connect"`, `button_href="/settings/connect_agent"`) and `TerminalIcon` in its `icon` slot. No new row in `sections`.

2. **`connect_agent/connect_agent.ts`.** New module, no DOM at import:

   ```ts
   export const DEFAULT_ORIGIN = "http://localhost:8757"
   export const MCP_PATH = "/mcp"
   export const AGENT_INSTALL_GUIDE_URL =
     "https://raw.githubusercontent.com/Kiln-AI/Kiln/main/agent_install.md"
   export const BASE_PROMPT = `Install Kiln's app, skill, and MCP following the guide here: ${AGENT_INSTALL_GUIDE_URL}`
   export function app_origin(is_dev: boolean = dev): string        // base_url in dev, else window.location.origin
   export function mcp_url(origin: string): string                   // origin without trailing slashes + MCP_PATH
   export function is_default_address(origin: string): boolean       // http:, port 8757, host localhost / 127.0.0.1 / [::1]; unparsable → false
   export function build_prompt(origin: string): string              // BASE_PROMPT, plus " The Kiln MCP server is at <url>." off the default
   ```

3. **`connect_agent/copy_button.svelte`.** Route-local button: props `text`, `what`, `primary = false`, `testid = null`. One `<button type="button" class="btn btn-sm w-20 flex-shrink-0">` (+ `btn-primary`), `aria-label` `Copy ${what}` / `Copied ${what}`, label `Copy` / `Copied`, then an `sr-only` `aria-live="polite"` span. `copy()` writes to the clipboard in a `try`, sets `copied`, restarts a 1500 ms timer; `catch` does nothing; `onDestroy` clears the timer.

4. **`connect_agent/+page.svelte`.** `agentInfo.set(...)`; constants `origin`, `url`, `prompt`; markup exactly as component doc 3.4: `AppPage` (title, subtitle, `Settings` breadcrumb, no docs link) → `flex flex-col gap-6 max-w-2xl` → `CalloutCard` with the lead-in, the prompt text and the primary Copy; the "Then ask your agent…" line; `Collapse` "Set up manually" with the URL row and a grey Copy. No `+page.ts`.

5. **`/agent_install.md`.** New file at the repo root with the full draft of component doc 4.3.

6. **`/README.md`.** The section `## Use Kiln from your coding agent` after `## App Quickstart` (component doc 5), and one Highlights bullet after the AI Assistant bullet. The emoji is a placeholder for a person to pick, so it is marked with a `TODO` comment in the Markdown for the owner.

7. **Rename** (component doc 6). Module docstrings of `libs/server/kiln_server/mcp/{__init__.py,mcp.py,runtime.py,tool_selection.py,mcp_server_tool_utils.py}`; the argparse `description` in `mcp.py`; `libs/server/kiln_server/mcp/README.md` title, second note, intro sentence and the `--help` block replaced with the real output; `libs/server/README.md` heading and sentence; `.agents/skills/kiln-conventions/references/server_desktop.md` startup row and a new "Where things go" row. `server_name` and `instructions` in `runtime.py` stay.

## Tests

`app/web_ui/src/routes/(app)/settings/page.test.ts` (added cases):

- connect callout shows with no update: title, description, link `/settings/connect_agent` with text "Connect"; update callout absent
- connect callout hidden when `has_update` is true; update callout present
- connect callout shows while the check is loading (`update_result: null`) and precedes the first `h2`

`connect_agent/connect_agent.test.ts` (node):

- `mcp_url` appends `/mcp`, strips trailing slashes, keeps a non-default host and port
- `is_default_address` true for localhost, 127.0.0.1, [::1] on 8757 (and a trailing slash); false for another port, https, a LAN IP, another host name, a non-URL
- `build_prompt` gives `BASE_PROMPT` on default addresses and the extra sentence otherwise; `BASE_PROMPT` starts with the fixed lead and ends with `AGENT_INSTALL_GUIDE_URL`
- `app_origin(true)` is `base_url`; `app_origin(false)` is the stubbed `window.location.origin`
- README has a line equal to `BASE_PROMPT` and the section heading
- `agent_install.md` holds the exact stub text, the MCP URL, the ping URL, the download link and the four agent headings, has at most 130 lines, and does not contain `AGENT_INSTALL_GUIDE_URL`

`connect_agent/page.test.ts` (jsdom, `app_origin` mocked, fake timers, `navigator.clipboard.writeText` mocked):

- prompt and URL on the default address, on `127.0.0.1:8757` and on `localhost:9000`
- header: title, subtitle, no "Read the Docs", breadcrumb to `/settings`; lead-in and "what next" lines
- Copy prompt and Copy URL each write their own text, show "Copied", return to "Copy" after 1500 ms, and do not change the other button
- clipboard rejects, and clipboard missing: no throw, label stays "Copy"
- "Set up manually" closed by default; exactly one `btn-primary`; accessible names "Copy prompt" and "Copy MCP server URL"; unmount during a running timer does not throw

`libs/server/kiln_server/mcp/test_mcp_server.py` (added cases):

- the server built by `create_fastmcp_server` still has a name starting with `Kiln MCP Server`
- `build_argument_parser().description` starts with "Run the Kiln project tools MCP server"

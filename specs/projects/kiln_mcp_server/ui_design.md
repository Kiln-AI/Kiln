---
status: complete
---

# UI Design: Kiln MCP Server

The only UI in this project is the "Connect your agent" page and the way into it. Follow the app's existing patterns; nothing here needs a new component.

## Entry point: a callout on Settings

For now, the only way in is a highlighted callout at the top of the Settings page, in our usual callout style (the same `Callout` component the "Update Available" notice uses there).

- Title: **Connect to Claude, Codex, and more**
- Description: **Use Kiln from your own agent.**
- Button: **Connect**, which opens `/settings/connect_agent`.
- Only one callout shows at a time. When the "Update Available" callout is showing, this one is hidden. Otherwise it is always shown; it is not dismissible in V1.

There is no row for it in the settings sections, and no other entry point in V1.

## The page: `/settings/connect_agent`

A standard `AppPage`, with a breadcrumb back to Settings.

- **Title:** Connect Your Agent
- **Subtitle:** Use Kiln from Claude Code, Codex, and other agents.
- **Docs link:** none for now. When the docs page for this feature is live, a "Read the Docs" link goes in the usual `AppPage` location under the subtitle.

Content, top to bottom. The page reads like a field of the Edit Task form: a form label and description over the content, read-only text in the app's `Output` block (grey, with its copy icon). The blue highlight is the Settings promotion; it is not used on this page.

```
Setup Prompt                                                  (i)
Paste this into your agent. Then ask it to work with Kiln.
┌─────────────────────────────────────────────────────────────┐
│ Install Kiln's app, skill, and MCP following the guide   ⧉  │
│ here: https://raw.githubusercontent.com/.../agent_install.md │
└─────────────────────────────────────────────────────────────┘

▸ Set Up Manually
    MCP Server URL                                            (i)
    Add this to your agent as an HTTP MCP server.
    ┌─────────────────────────────────────────────────────────┐
    │ http://localhost:8757/mcp                            ⧉  │
    └─────────────────────────────────────────────────────────┘
```

1. **Setup Prompt.** The main thing on the page. A form label ("Setup Prompt") with one line of description that also says what to do next, and an info tooltip that says what the agent will do (check Kiln is running, add the MCP server, create a Kiln skill). The prompt itself is plain, selectable text in an `Output`, copied with its copy icon.
2. **Set Up Manually.** A collapse, closed by default. It holds only the MCP server URL: a form label, one line of description, an info tooltip with the transport, authentication and timeout, and the URL in an `Output` with its copy icon. Plain text, not bold.

No status indicators, no per-agent tabs or commands, no list of connected agents and no primary button.

## States

- **Default address.** The prompt is exactly the one line above, and the manual URL is `http://localhost:8757/mcp`.
- **Kiln on another address.** The manual URL shows the real address. The prompt shown and copied gets one extra sentence that states the real MCP URL (for example "The Kiln MCP server is at http://localhost:9000/mcp."), on its own line after a blank line, because the guide can only name the default.
- There is no loading or error state: everything on the page is known to the app without a slow call.

## Responsive behavior

The page is a single column as wide as the Edit Task form. The prompt and URL wrap; their copy icons stay visible at any width.

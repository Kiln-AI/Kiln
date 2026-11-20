---
status: complete
---

# UI Design: Kiln MCP Server

The only UI in this project is the "Connect your agent" page and the way into it. Follow the app's existing patterns; nothing here needs a new component.

## Entry point: a callout on Settings

For now, the only way in is a highlighted callout at the top of the Settings page, in our usual callout style (the same `Callout` component the "Update Available" notice uses there).

- Title: **Connect Kiln to Claude, Codex, OpenCode and more**
- Description: one line, for example "Use Kiln from your own coding agent."
- Button: **Connect**, which opens `/settings/connect_agent`.
- Only one callout shows at a time. When the "Update Available" callout is showing, this one is hidden. Otherwise it is always shown; it is not dismissible in V1.

There is no row for it in the settings sections, and no other entry point in V1.

## The page: `/settings/connect_agent`

A standard `AppPage`, with a breadcrumb back to Settings.

- **Title:** Connect Your Agent
- **Subtitle:** Use Kiln from Claude Code, Codex, OpenCode and other coding agents.
- **Docs link:** in the usual `AppPage` location under the subtitle ("Read the Docs"), linking to the docs page for this feature.

Content, top to bottom:

```
┌─────────────────────────────────────────────────────────────┐
│ Paste this in your agent to get started:                    │
│                                                             │
│   Install Kiln's app, skill, and MCP following the guide    │
│   here: https://kiln.tech/agent_install.md                  │
│                                                  [ Copy ]   │
└─────────────────────────────────────────────────────────────┘

Then ask your agent to work with Kiln, or type /kiln.

▸ Set up manually
    MCP server URL:  http://localhost:8757/mcp     [ Copy ]
```

1. **The prompt box.** The main thing on the page. It shows the prompt as plain, selectable text, with a Copy button. Copy gives the usual "copied" feedback.
2. **One line of "what next":** "Then ask your agent to work with Kiln, or type /kiln."
3. **Set up manually.** Collapsed by default. It holds only the MCP server URL with its own Copy button, for people who want to configure an agent by hand.

No status indicators, no per-agent tabs or commands, and no list of connected agents.

## States

- **Default address.** The prompt is exactly the one line above, and the manual URL is `http://localhost:8757/mcp`.
- **Kiln on another address.** The manual URL shows the real address. The prompt shown and copied gets one extra sentence that states the real MCP URL (for example "The Kiln MCP server is at http://localhost:9000/mcp."), because the guide can only name the default.
- There is no loading or error state: everything on the page is known to the app without a slow call.

## Responsive behavior

The page is a single narrow column, like the other settings pages. The prompt text wraps; the Copy button stays visible at any width.

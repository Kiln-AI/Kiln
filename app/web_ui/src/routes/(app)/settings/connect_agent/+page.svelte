<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import CalloutCard from "$lib/ui/callout_card.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { agentInfo } from "$lib/agent"
  import CopyButton from "./copy_button.svelte"
  import { app_origin, build_prompt, mcp_url } from "./connect_agent"

  agentInfo.set({
    name: "Connect Your Agent",
    description:
      "Shows the prompt and the MCP server URL for connecting a coding agent (Claude Code, Codex, OpenCode) to Kiln's MCP server.",
  })

  const origin = app_origin()
  const url = mcp_url(origin)
  const prompt = build_prompt(origin)
</script>

<AppPage
  title="Connect Your Agent"
  subtitle="Use Kiln from Claude Code, Codex, OpenCode and other coding agents."
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
>
  <div class="flex flex-col gap-6 max-w-2xl">
    <CalloutCard testid="connect-agent-prompt-card">
      <div class="flex flex-col gap-3">
        <p class="text-sm text-gray-500">
          Paste this in your agent to get started:
        </p>
        <div class="flex flex-col sm:flex-row sm:items-end gap-3">
          <p
            class="flex-grow min-w-0 text-base font-medium break-words select-all"
            translate="no"
            data-testid="connect-agent-prompt"
          >
            {prompt}
          </p>
          <CopyButton
            text={prompt}
            what="prompt"
            primary
            testid="connect-agent-copy-prompt"
          />
        </div>
      </div>
    </CalloutCard>
    <p class="text-sm text-gray-500">
      Then ask your agent to work with Kiln, or type /kiln.
    </p>
    <!-- Outlined: on the default grey fill, the grey Copy button inside would read as part of the surface. -->
    <Collapse title="Set up manually" outlined>
      <div class="flex flex-row items-center gap-3">
        <div class="flex-grow min-w-0 text-sm">
          <span class="text-gray-500">MCP server URL:</span>
          <span
            class="break-words select-all"
            translate="no"
            data-testid="connect-agent-mcp-url">{url}</span
          >
        </div>
        <CopyButton
          text={url}
          what="MCP server URL"
          testid="connect-agent-copy-url"
        />
      </div>
    </Collapse>
  </div>
</AppPage>

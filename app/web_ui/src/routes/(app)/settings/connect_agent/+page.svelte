<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Output from "$lib/ui/output.svelte"
  import { agentInfo } from "$lib/agent"
  import { app_origin, build_prompt, mcp_url } from "./connect_agent"

  agentInfo.set({
    name: "Connect Your Agent",
    description:
      "Shows the prompt and the MCP server URL for connecting an agent (Claude Code, Codex, OpenCode or another) to Kiln's MCP server.",
  })

  const origin = app_origin()
  const url = mcp_url(origin)
  const prompt = build_prompt(origin)
</script>

<AppPage
  title="Connect Your Agent"
  subtitle="Use Kiln from Claude Code, Codex, and other agents."
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
>
  <div class="max-w-[900px] flex flex-col gap-6">
    <div>
      <FormElement
        inputType="header_only"
        id="connect_agent_prompt"
        label="Setup Prompt"
        description="Paste this into your agent. Then ask it to work with Kiln."
        info_description="Your agent follows Kiln's install guide: it checks that Kiln is running, adds the Kiln MCP server to its settings and creates a Kiln skill."
        value=""
      />
      <div data-testid="connect-agent-prompt">
        <Output raw_output={prompt} />
      </div>
    </div>
    <Collapse title="Set Up Manually">
      <div>
        <FormElement
          inputType="header_only"
          id="connect_agent_mcp_url"
          label="MCP Server URL"
          description="Add this to your agent as an HTTP MCP server."
          info_description="Use the HTTP transport (also called streamable HTTP), with no authentication. If your agent has a tool timeout, set it to 30 minutes: some Kiln calls take minutes."
          value=""
        />
        <div data-testid="connect-agent-mcp-url">
          <Output raw_output={url} show_border />
        </div>
      </div>
    </Collapse>
  </div>
</AppPage>

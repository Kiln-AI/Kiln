<script lang="ts">
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Assistant Kiln Pro Auth",
    description:
      "Authentication page for Kiln Pro access to use Kiln Assistant.",
  })
</script>

<CopilotAuthPage
  title="Kiln Assistant"
  docs_link="https://docs.kiln.tech"
  breadcrumbs={[{ label: "Assistant", href: "/assistant" }]}
  success_redirect_url="/assistant"
/>

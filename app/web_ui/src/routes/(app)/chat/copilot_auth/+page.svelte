<script lang="ts">
  import CopilotAuthPage from "$lib/ui/kiln_copilot/copilot_auth_page.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Chat Copilot Auth",
    description:
      "Authentication page for Kiln Copilot access to use Kiln Chat.",
  })
</script>

<CopilotAuthPage
  title="Kiln Chat"
  docs_link="https://docs.kiln.tech"
  breadcrumbs={[{ label: "Chat", href: "/chat" }]}
  success_redirect_url="/chat"
  cancel_redirect_url="/chat"
/>

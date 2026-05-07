<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { goto } from "$app/navigation"
  import ConnectKilnCopilot from "../../../../(fullscreen)/setup/(setup)/connect_providers/kiln_pro/connect_kiln_copilot.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Kiln Pro",
    description: "Connect to Kiln Pro for AI-assisted features.",
  })
</script>

<AppPage
  title="Kiln Pro"
  breadcrumbs={[
    { label: "Settings", href: "/settings" },
    { label: "AI Providers", href: "/settings/providers" },
  ]}
>
  <ConnectKilnCopilot
    onSuccess={() => goto("/settings/providers")}
    onCancel={() => goto("/settings/providers")}
  />
</AppPage>

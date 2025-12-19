<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { goto } from "$app/navigation"
  import ConnectKilnCopilot from "../../../../(fullscreen)/setup/(setup)/connect_providers/kiln_copilot/connect_kiln_copilot.svelte"
</script>

<AppPage
  title="Connect Kiln Copilot"
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

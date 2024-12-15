<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import ConnectProviders from "../../../(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte"
</script>

<AppPage
  title="AI Providers & Models"
  action_buttons={[
    {
      label: "Add Models",
      href: "/settings/providers/add_models",
      primary: true,
    },
  ]}
>
  <ConnectProviders />
</AppPage>

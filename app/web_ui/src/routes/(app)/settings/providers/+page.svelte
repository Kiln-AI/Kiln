<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import ConnectProviders from "../../../(fullscreen)/setup/(setup)/connect_providers/connect_providers.svelte"
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"
</script>

<AppPage
  title={$_("settings.ai_providers")}
  sub_subtitle={$_("settings.read_the_docs")}
  sub_subtitle_link="https://docs.getkiln.ai/docs/models-and-ai-providers"
  action_buttons={[
    {
      label: $_("providers.add_models"),
      href: "/settings/providers/add_models",
      primary: true,
    },
  ]}
>
  <ConnectProviders
    highlight_finetune={$page.url.searchParams.get("highlight") === "finetune"}
  />
</AppPage>

<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import Tutorial from "../../../(fullscreen)/setup/(setup)/intro/tutorial.svelte"
  import { agentInfo } from "$lib/agent"

  agentInfo.set({
    name: "Introduction",
    description: "Getting started tutorial and introduction to Kiln.",
  })
</script>

<AppPage title="Introduction">
  <Tutorial />
</AppPage>

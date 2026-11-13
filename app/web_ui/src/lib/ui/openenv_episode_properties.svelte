<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import type { OpenEnvEpisode } from "$lib/types"
  import { load_openenv_server } from "$lib/api/openenv_server_api"
  import {
    openenv_server_detail_link,
    format_reset_arguments,
  } from "$lib/utils/openenv"

  export let project_id: string
  export let episode: OpenEnvEpisode

  // Shows the arguments the session started with, not the preset's name:
  // presets can be renamed or removed after the run.
  $: openenv_server_id = episode.reset.openenv_server_id
  let openenv_server_name: string | null = null
  let latest_load = 0

  $: load_name(project_id, openenv_server_id)

  async function load_name(project_id: string, openenv_server_id: string) {
    const load = ++latest_load
    openenv_server_name = null
    try {
      const openenv_server = await load_openenv_server(
        project_id,
        openenv_server_id,
      )
      if (load === latest_load) {
        openenv_server_name = openenv_server.name
      }
    } catch {
      // A removed OpenEnv server still has its id on the run, which is shown instead.
    }
  }

  let properties: UiProperty[]
  $: properties = [
    {
      name: "OpenEnv Server",
      value: openenv_server_name ?? openenv_server_id,
      link: openenv_server_detail_link(project_id, openenv_server_id),
    },
    { name: "Version", value: episode.openenv_version },
    {
      name: "Reset Arguments",
      value: format_reset_arguments(episode.reset.reset_kwargs),
      use_custom_slot: true,
    },
  ]
</script>

<PropertyList {properties} title="OpenEnv">
  <svelte:fragment slot="custom_value" let:property>
    <pre
      class="min-w-0 font-mono text-sm whitespace-pre-wrap break-all">{property.value}</pre>
  </svelte:fragment>
</PropertyList>

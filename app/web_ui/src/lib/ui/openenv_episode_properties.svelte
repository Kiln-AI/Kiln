<script lang="ts">
  import PropertyList from "$lib/ui/property_list.svelte"
  import SeeAllDialog from "$lib/ui/see_all_dialog.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import type { OpenEnvEpisode, OpenEnvServer } from "$lib/types"
  import { load_openenv_server } from "$lib/api/openenv_server_api"
  import {
    openenv_server_detail_link,
    format_reset_arguments,
    matching_preset_name,
  } from "$lib/utils/openenv"

  export let project_id: string
  export let episode: OpenEnvEpisode

  $: openenv_server_id = episode.reset.openenv_server_id
  let openenv_server: OpenEnvServer | null = null
  let latest_load = 0

  $: load_server(project_id, openenv_server_id)

  async function load_server(project_id: string, openenv_server_id: string) {
    const load = ++latest_load
    openenv_server = null
    try {
      const loaded = await load_openenv_server(project_id, openenv_server_id)
      if (load === latest_load) {
        openenv_server = loaded
      }
    } catch {
      // A removed OpenEnv server still has its id on the run, which is shown instead.
    }
  }

  let reset_arguments_dialog: SeeAllDialog

  // The run stores the arguments the session started with, not the preset's
  // name, since presets can be renamed or removed after the run. When a saved
  // preset still has exactly these arguments, it's shown by name; otherwise
  // the list shows how many arguments there were. Either opens the JSON.
  $: preset_name = matching_preset_name(
    openenv_server,
    episode.reset.reset_kwargs,
  )
  $: reset_argument_count = Object.keys(episode.reset.reset_kwargs ?? {}).length

  function show_reset_arguments(title: string) {
    reset_arguments_dialog.show(
      title,
      format_reset_arguments(episode.reset.reset_kwargs),
    )
  }

  let properties: UiProperty[]
  $: properties = [
    {
      name: "OpenEnv Server",
      value: openenv_server?.name ?? openenv_server_id,
      link: openenv_server_detail_link(project_id, openenv_server_id),
    },
    { name: "Version", value: episode.openenv_version },
    preset_name
      ? {
          name: "Environment Preset",
          value: preset_name,
          action: () => show_reset_arguments(preset_name ?? ""),
        }
      : reset_argument_count === 0
        ? { name: "Environment Options", value: "None" }
        : {
            name: "Environment Options",
            value:
              reset_argument_count === 1
                ? "1 option"
                : `${reset_argument_count} options`,
            action: () => show_reset_arguments("Environment Options"),
          },
  ]
</script>

<PropertyList {properties} title="OpenEnv" />
<SeeAllDialog bind:this={reset_arguments_dialog} />

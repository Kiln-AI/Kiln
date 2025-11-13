<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { TaskRunConfig } from "$lib/types"
  import { model_info } from "$lib/stores"
  import { prompts_by_task_composite_id } from "$lib/stores/prompts_store"
  import { available_tools } from "$lib/stores"
  import { get_task_composite_id } from "$lib/stores"
  import { getRunConfigUiProperties } from "$lib/utils/run_config_formatters"

  export let project_id: string
  export let task_id: string
  export let task_run_config: TaskRunConfig

  let dialog: Dialog | null = null

  export function show() {
    dialog?.show()
  }

  $: task_prompts =
    $prompts_by_task_composite_id[get_task_composite_id(project_id, task_id)] ||
    null

  $: properties = getRunConfigUiProperties(
    project_id,
    task_id,
    task_run_config,
    $model_info,
    task_prompts,
    $available_tools,
  )
</script>

<Dialog bind:this={dialog} title="Run Configuration Details" width="wide">
  <PropertyList {properties} />
</Dialog>

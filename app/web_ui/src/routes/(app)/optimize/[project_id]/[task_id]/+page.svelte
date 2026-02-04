<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import OptimizeCard from "$lib/ui/optimize_card.svelte"
  import { get_optimizers } from "./optimizers"
  import { page } from "$app/stores"
  import SettingsHeader from "$lib/ui/settings_header.svelte"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: optimizers = get_optimizers(project_id, task_id)
</script>

<AppPage
  title="Optimize"
  subtitle="Optimize your current task for better performance with prompts, models and more."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/optimize"
>
  <div class="flex flex-col gap-6">
    <SettingsHeader title="Select Optimization" />
    <div
      class="grid gap-6"
      style="grid-template-columns: repeat(auto-fit, minmax(300px, 350px));"
    >
      {#each optimizers as optimizer}
        <OptimizeCard
          title={optimizer.title}
          description={optimizer.description}
          cost={optimizer.cost}
          effort={optimizer.effort}
          onClick={optimizer.onClick}
        />
      {/each}
    </div>
    <SettingsHeader title="Run Configurations" />
  </div>
</AppPage>

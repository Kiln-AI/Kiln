<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import OptimizeCard from "$lib/ui/optimize_card.svelte"
  import { get_optimizers } from "./optimizers"
  import { page } from "$app/stores"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: optimizers = get_optimizers(project_id, task_id)
</script>

<AppPage
  title="Optimize"
  subtitle="Optimize your current task for better performance."
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/optimize"
>
  <div class="overflow-x-auto">
    <div
      class="grid gap-6"
      style="grid-template-columns: repeat(auto-fit, minmax(300px, 350px));"
    >
      {#each optimizers as optimizer}
        <OptimizeCard
          title={optimizer.title}
          description={optimizer.description}
          info_description={optimizer.info_description}
          cost={optimizer.cost}
          complexity={optimizer.complexity}
          speed={optimizer.speed}
          onClick={optimizer.onClick}
        />
      {/each}
    </div>
  </div>
</AppPage>

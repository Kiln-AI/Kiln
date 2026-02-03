<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import OptimizeCard from "$lib/ui/optimize_card.svelte"
  import { optimizers } from "./optimizers"
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Optimize"
    subtitle="Optimize your current task for better performance."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/optimize"
  >
    <div class="overflow-x-auto">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
</div>

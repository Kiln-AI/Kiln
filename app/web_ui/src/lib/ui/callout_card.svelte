<script lang="ts">
  // Reusable callout card — a primary-tinted container with the same visual
  // treatment as the "Update Available" banner (border-primary/30 + bg-primary/5).
  //
  // Provides a default slot for arbitrary content and an optional "icon" slot
  // rendered inside a circular primary-tinted bubble (matches the callout.svelte
  // icon treatment). When no icon slot is provided the bubble is omitted.
  //
  // Usage:
  //   <CalloutCard>
  //     <p>Any content here</p>
  //   </CalloutCard>
  //
  //   <CalloutCard>
  //     <svelte:fragment slot="icon"><MyIcon /></svelte:fragment>
  //     <p>Content with a leading icon</p>
  //   </CalloutCard>
  export let testid: string | null = null
</script>

<div
  class="card card-bordered border-primary/30 bg-primary/5 shadow-sm rounded-md"
  data-testid={testid}
>
  <div class="flex flex-row items-start gap-4 p-4">
    {#if $$slots.icon}
      <div
        class="flex-shrink-0 w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center"
      >
        <div class="w-5 h-5">
          <slot name="icon" />
        </div>
      </div>
    {/if}
    <div class="flex-grow min-w-0">
      <slot />
    </div>
  </div>
</div>

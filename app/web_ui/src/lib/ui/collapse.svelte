<script lang="ts">
  export let title: string
  export let description: string | null = null
  export let small: boolean = true
  export let badge: string | null = null
  export let badge_position: "left" | "right" = "left"
  export let badge_data_tip: string | null = null
  export let open: boolean = false
</script>

<div
  class="collapse collapse-arrow bg-base-200 {small
    ? 'collapse-sm'
    : 'collapse-md'}"
>
  <input type="checkbox" class="peer min-h-[24px]" bind:checked={open} />
  <div
    class="collapse-title font-medium flex flex-col {small
      ? 'text-sm'
      : ''} min-h-[24px]"
  >
    <div class="flex flex-row items-center">
      {#if badge_position === "right"}
        {title}
      {/if}
      {#if badge}
        <span
          class="badge badge-outline {badge_position === 'right'
            ? 'ml-2'
            : 'mr-2'} px-1 text-xs min-w-[20px] {badge_data_tip
            ? 'tooltip tooltip-right relative z-10 pointer-events-auto'
            : ''}"
          data-tip={badge_data_tip}>{badge}</span
        >
      {/if}
      {#if badge_position === "left"}
        {title}
      {/if}
    </div>
    {#if description}
      <div class="text-{small ? 'xs' : 'sm'} text-gray-500">
        {description}
      </div>
    {/if}
  </div>
  <div class="collapse-content flex flex-col gap-4" style="min-width: 0">
    <slot />
  </div>
</div>

<style>
  .collapse-sm input {
    max-height: 44px;
  }

  .collapse-sm .collapse-title::after {
    top: 1.4rem;
  }

  .collapse-sm .collapse-title {
    padding-top: 12px;
    padding-bottom: 12px;
  }
</style>

<script lang="ts">
  export let title: string
  export let subtitle: string | null = null
</script>

<div class="pb-3 border-b border-gray-200">
  {#if $$slots.actions}
    <!-- Actions ride on the title's line, right-aligned and bottom-aligned
         with it, inside the header's own rule so the rule still runs the full
         width. The title markup is repeated rather than wrapped for every
         caller: a header with no actions renders exactly what it always did. -->
    <div class="flex items-end justify-between gap-3">
      <div class="min-w-0">
        <h2 class="text-lg font-medium text-gray-900">{title}</h2>
        {#if subtitle}
          <p class="text-sm text-gray-500">{subtitle}</p>
        {/if}
      </div>
      <!-- The control spaces the actions, so two headers with two buttons
           never drift apart at their call sites. -->
      <div class="flex items-center gap-2 flex-none">
        <slot name="actions" />
      </div>
    </div>
  {:else}
    <h2 class="text-lg font-medium text-gray-900">{title}</h2>
    {#if subtitle}
      <p class="text-sm text-gray-500">{subtitle}</p>
    {/if}
  {/if}
</div>

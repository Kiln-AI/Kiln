<script lang="ts">
  export let title: string
  export let subtitle: string = ""
  export let testid: string = ""
</script>

<div class="flex flex-col gap-3" data-testid={testid || undefined}>
  <div>
    <h3 class="text-sm font-medium">{title}</h3>
    {#if subtitle}
      <p
        class="text-xs text-gray-500 mt-0.5"
        data-testid="form-section-subtitle"
      >
        {subtitle}
      </p>
    {/if}
  </div>
  <slot />
</div>

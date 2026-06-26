<script lang="ts">
  export let title: string
  export let subtitle: string = ""
  export let testid: string = ""
</script>

<div class="flex flex-col gap-3" data-testid={testid || undefined}>
  <div>
    <h3 class="text-base font-medium">{title}</h3>
    {#if subtitle}
      <p
        class="text-sm text-gray-500 font-light mt-0.5"
        data-testid="form-section-subtitle"
      >
        {subtitle}
      </p>
    {/if}
  </div>
  <slot />
</div>

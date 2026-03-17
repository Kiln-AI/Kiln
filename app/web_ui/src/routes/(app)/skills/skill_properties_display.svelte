<script lang="ts">
  import Output from "$lib/ui/output.svelte"
  import { skill_field_configs } from "./skill_field_configs"

  export let description: string | null | undefined
  export let body: string | null | undefined

  const properties = {
    description,
    body,
  }

  function getPropertyValue(key: string): string | undefined {
    const value = properties[key as keyof typeof properties]
    return value ?? undefined
  }
</script>

<div class="flex flex-col gap-6">
  {#each skill_field_configs as field (field.key)}
    {@const value = getPropertyValue(field.key)}
    {#if value && value.trim()}
      <div>
        <div class="text-sm font-medium text-left">
          {field.label}
        </div>
        <div class="text-xs font-medium text-gray-500 mt-1">
          {field.description}
        </div>
        <div class="mt-1">
          <Output raw_output={value} />
        </div>
      </div>
    {/if}
  {/each}
</div>

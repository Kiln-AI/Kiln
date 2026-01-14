<script lang="ts">
  import type { SpecType } from "$lib/types"
  import { spec_field_configs } from "./select_template/spec_templates"

  export let spec_type: SpecType
  export let properties: Record<string, string | null | undefined>

  function getPropertyValue(key: string): string | undefined {
    const value = properties[key]
    return value ?? undefined
  }
</script>

<div class="flex flex-col gap-6">
  {#each spec_field_configs[spec_type] as field (field.key)}
    {@const value = getPropertyValue(field.key)}
    {#if value && value.trim()}
      <div>
        <div class="text-sm font-medium text-left">
          {field.label}
        </div>
        <div class="text-xs text-gray-500 mt-1">
          {field.description}
        </div>
        <div
          class="rounded-lg p-4 mt-1 prose prose-sm max-w-none whitespace-pre-wrap
            bg-base-200"
        >
          {value}
        </div>
      </div>
    {/if}
  {/each}
</div>

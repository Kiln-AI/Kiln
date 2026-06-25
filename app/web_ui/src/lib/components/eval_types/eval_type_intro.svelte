<script lang="ts">
  import type { V2EvalTypeMetadata } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./select/eval_type_tags.svelte"

  export let metadata: V2EvalTypeMetadata
</script>

<div class="pb-6" data-testid="eval-type-intro">
  <div class="flex items-start gap-3">
    <div
      class="flex items-center justify-center w-9 h-9 rounded-lg bg-base-200 flex-none mt-0.5"
    >
      <i class="{metadata.icon} text-lg text-primary"></i>
    </div>

    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-1">
        <h2 class="font-medium text-base">{metadata.label}</h2>
        {#if metadata.tags.length > 0}
          <EvalTypeTags tags={metadata.tags} />
        {/if}
      </div>
      <p class="text-sm text-gray-500 leading-relaxed">
        {metadata.explainer || metadata.description}
      </p>
      {#if metadata.example}
        <p class="text-sm text-gray-400 italic mt-1.5">
          {metadata.example}
        </p>
      {/if}
    </div>
  </div>
</div>

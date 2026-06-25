<script lang="ts">
  import type { V2EvalTypeMetadata } from "$lib/utils/eval_types/registry"

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
      <h2 class="font-medium text-base mb-1">{metadata.label}</h2>
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

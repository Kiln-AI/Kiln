<script lang="ts">
  import type {
    V2EvalType,
    V2EvalTypeMetadata,
  } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./select/eval_type_tags.svelte"
  import CalloutCard from "$lib/ui/callout_card.svelte"
  import EvalTypeIcon from "$lib/components/eval_types/eval_type_icon.svelte"

  export let evalType: V2EvalType
  export let metadata: V2EvalTypeMetadata
</script>

<div class="pb-6" data-testid="eval-type-intro">
  <CalloutCard testid="eval-type-intro-card">
    <div
      slot="icon"
      class="flex items-center justify-center w-full h-full"
      aria-hidden="true"
    >
      <EvalTypeIcon {evalType} />
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
        <p class="text-sm text-gray-500 italic mt-1.5">
          {metadata.example}
        </p>
      {/if}
    </div>
  </CalloutCard>
</div>

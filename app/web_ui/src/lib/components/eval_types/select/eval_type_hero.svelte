<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { V2EvalTypeMetadata } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./eval_type_tags.svelte"

  export let metadata: V2EvalTypeMetadata

  const dispatch = createEventDispatcher<{ continue: void }>()
</script>

<div
  class="card card-bordered border-base-300 border-2 shadow-md bg-base-200 p-6"
>
  <div class="flex items-center gap-5">
    <div
      class="flex items-center justify-center w-12 h-12 rounded-lg bg-base-100 flex-none"
    >
      <i class="{metadata.icon} text-2xl text-primary"></i>
    </div>

    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-1">
        <span class="font-medium text-base">{metadata.label}</span>
        {#if metadata.recommended}
          <span class="badge badge-sm badge-primary">&#9733; Recommended</span>
        {/if}
      </div>
      <p class="text-sm text-base-content/60 mb-2">
        {metadata.description}
      </p>
      <EvalTypeTags tags={metadata.tags} />
    </div>

    <button
      class="btn btn-primary btn-sm flex-none"
      on:click|stopPropagation={() => dispatch("continue")}
    >
      Continue
    </button>
  </div>
</div>

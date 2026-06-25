<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { V2EvalTypeMetadata } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./eval_type_tags.svelte"

  export let metadata: V2EvalTypeMetadata

  const dispatch = createEventDispatcher<{ select: void }>()
</script>

<button
  data-testid="eval-type-row"
  class="card card-bordered border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 p-4 w-full text-left cursor-pointer"
  on:click={() => dispatch("select")}
>
  <div class="flex items-center gap-4">
    <div
      class="flex items-center justify-center w-9 h-9 rounded-lg bg-base-200 flex-none"
    >
      <i class="{metadata.icon} text-lg text-primary"></i>
    </div>

    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="font-medium text-sm whitespace-nowrap"
          >{metadata.label}</span
        >
        <EvalTypeTags tags={metadata.tags} />
      </div>
      <p class="text-xs text-gray-500 mt-0.5">
        {metadata.description}
      </p>
    </div>

    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="currentColor"
      class="flex-none text-gray-400"
    >
      <path
        fill-rule="evenodd"
        d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"
      />
    </svg>
  </div>
</button>

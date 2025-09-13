<script lang="ts">
  import type { Trace } from "$lib/types"

  export let trace: Trace
</script>

<div class="flex flex-col gap-2">
  {#each trace ?? [] as message}
    <div class="flex flex-col gap-2">
      <div class="flex flex-col gap-2">
        <div class="font-medium">{message.role}</div>
        <div class="text-sm">{message.content}</div>
      </div>
    </div>
  {/each}
</div>

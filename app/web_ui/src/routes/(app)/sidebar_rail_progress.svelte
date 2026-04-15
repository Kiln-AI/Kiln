<script lang="ts">
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import ProgressWidget from "$lib/ui/progress_widget.svelte"
  import Float from "$lib/ui/float.svelte"
</script>

{#if $progress_ui_state}
  <div class="flex justify-center relative py-2">
    <div
      class="w-3 h-3 rounded-full bg-primary"
      aria-label="In progress"
      role="img"
    ></div>
    <Float placement="right-start" offset_px={12} role="presentation">
      <ProgressWidget />
    </Float>
  </div>
{/if}

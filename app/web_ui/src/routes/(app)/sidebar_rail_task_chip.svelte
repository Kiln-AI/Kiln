<script lang="ts">
  import { current_task, current_project } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import Float from "$lib/ui/float.svelte"

  const dispatch = createEventDispatcher<{ open: void }>()

  $: taskName = $current_task?.name ?? ""
  $: projectName = $current_project?.name ?? ""
  $: letter = taskName ? taskName[0].toUpperCase() : ""
  $: hasTooltip = taskName !== "" || projectName !== ""

  let hovered = false
  let focused = false
  $: show_tooltip = hasTooltip && (hovered || focused)
</script>

<div class="flex justify-center my-1">
  <button
    class="relative w-8 h-8 rounded-md border border-base-300 bg-base-100 text-sm font-medium flex items-center justify-center"
    on:click={() => dispatch("open")}
    on:mouseenter={() => (hovered = true)}
    on:mouseleave={() => (hovered = false)}
    on:focus={() => (focused = true)}
    on:blur={() => (focused = false)}
    aria-label={taskName || "Select task"}
  >
    {letter}
    {#if show_tooltip}
      <Float placement="right" offset_px={8} role="tooltip" portal>
        <span
          class="pointer-events-none px-3 py-1.5 rounded bg-neutral text-neutral-content text-xs whitespace-nowrap flex flex-col items-start text-left shadow-md"
        >
          {#if taskName}
            <span class="font-medium">{taskName}</span>
          {/if}
          {#if projectName}
            <span class="text-gray-400">{projectName}</span>
          {/if}
        </span>
      </Float>
    {/if}
  </button>
</div>

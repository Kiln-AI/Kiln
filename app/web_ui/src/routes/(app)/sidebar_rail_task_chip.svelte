<script lang="ts">
  import { current_task, current_project } from "$lib/stores"
  import { createEventDispatcher } from "svelte"
  import SidebarRailTooltip from "./sidebar_rail_tooltip.svelte"

  const dispatch = createEventDispatcher<{ open: void }>()

  $: taskName = $current_task?.name ?? ""
  $: projectName = $current_project?.name ?? ""
  $: letter = taskName ? taskName[0].toUpperCase() : ""
  $: hasTooltip = taskName !== "" || projectName !== ""

  let hovered = false
  let focused = false
  $: show_tooltip = hasTooltip && (hovered || focused)

  // Unique id so we can wire aria-describedby on the trigger. The tooltip
  // content includes the project name, which is not part of the aria-label,
  // so assistive tech needs a way to reach it from the focused button.
  const tooltipId = `sidebar-rail-task-chip-tooltip-${crypto.randomUUID()}`
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
    aria-describedby={show_tooltip ? tooltipId : undefined}
  >
    {letter}
    <SidebarRailTooltip
      show={show_tooltip}
      variant="multi"
      role="tooltip"
      aria_hidden={false}
      id={tooltipId}
    >
      {#if taskName}
        <span class="font-medium">{taskName}</span>
      {/if}
      {#if projectName}
        <span class="text-gray-500">{projectName}</span>
      {/if}
    </SidebarRailTooltip>
  </button>
</div>

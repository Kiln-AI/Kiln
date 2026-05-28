<script lang="ts">
  import { active_jobs_count } from "$lib/stores/jobs_store"

  // "rail" overlays the count on a sidebar icon (absolute, top-right).
  // "inline" sits next to a label in the wide drawer.
  export let variant: "rail" | "inline" = "inline"

  // Defaults to the live active-jobs count, but accepts an override so the
  // component is render-testable in isolation.
  export let count: number | undefined = undefined

  $: resolved = count ?? $active_jobs_count
  $: label = resolved > 99 ? "99+" : `${resolved}`
</script>

{#if resolved > 0}
  {#if variant === "rail"}
    <span
      class="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-content text-[10px] leading-4 font-medium text-center"
      aria-label={`${resolved} active jobs`}
    >
      {label}
    </span>
  {:else}
    <span
      class="badge badge-sm badge-primary"
      aria-label={`${resolved} active jobs`}
    >
      {label}
    </span>
  {/if}
{/if}

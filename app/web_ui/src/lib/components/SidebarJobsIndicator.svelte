<script lang="ts">
  import { active_jobs_count, jobs } from "$lib/stores/jobs_store"
  import { jobs_indicator } from "$lib/stores/job_status"

  // "rail" overlays the indicator on a sidebar icon (absolute, top-right).
  // "inline" sits next to a label in the wide drawer.
  export let variant: "rail" | "inline" = "inline"

  // Default to the live counts, but accept overrides so the component is
  // render-testable in isolation.
  export let active_count: number | undefined = undefined
  export let total_count: number | undefined = undefined

  $: indicator = jobs_indicator(
    active_count ?? $active_jobs_count,
    total_count ?? $jobs.length,
  )
  $: label =
    indicator.kind === "hidden"
      ? ""
      : indicator.count > 99
        ? "99+"
        : `${indicator.count}`
  $: aria_label =
    indicator.kind === "spinner"
      ? `${indicator.count} active jobs`
      : indicator.kind === "static"
        ? `${indicator.count} jobs`
        : ""
</script>

{#if indicator.kind !== "hidden"}
  {#if variant === "rail"}
    <span
      class="absolute -top-1 -right-1 flex items-center gap-0.5 min-w-4 h-4 px-1 rounded-full text-[10px] leading-4 font-medium text-center {indicator.kind ===
      'spinner'
        ? 'bg-primary text-primary-content'
        : 'bg-base-300 text-base-content/70'}"
      aria-label={aria_label}
    >
      {#if indicator.kind === "spinner"}
        <span class="loading loading-spinner w-2 h-2" aria-hidden="true"></span>
      {/if}
      {label}
    </span>
  {:else}
    <span
      class="badge badge-sm inline-flex items-center gap-1 {indicator.kind ===
      'spinner'
        ? 'badge-primary'
        : 'badge-ghost text-base-content/70'}"
      aria-label={aria_label}
    >
      {#if indicator.kind === "spinner"}
        <span class="loading loading-spinner w-3 h-3" aria-hidden="true"></span>
      {/if}
      {label}
    </span>
  {/if}
{/if}

<script lang="ts">
  import SettingsGearIcon from "$lib/ui/icons/settings_gear_icon.svelte"

  // Friendly names of the selected input model + provider (e.g. "GPT-5.5",
  // "OpenRouter"). Empty until a model resolves.
  export let model_name: string = ""
  export let provider: string = ""
  // Opens the generation-settings dialog.
  export let open: () => void
</script>

<!-- Fixed width + right-aligned to match the compact (min-w-64, right-aligned)
Continue button below. Negative bottom margin tightens the FormContainer's
gap-6 (24px) row gap to the Continue button; use -mb-6 to close it fully. -->
<div class="w-full flex justify-end -mb-4">
  <div class="w-64 max-w-full">
    <!-- Eyebrow label: matches the Settings page section headers. -->
    <div
      class="text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5"
    >
      Generation Settings
    </div>
    <!-- `btn` (no color modifier) is the app's default gray button — same
    height/shape/hover as the primary Continue button below. -->
    <button
      type="button"
      on:click={open}
      class="btn w-full justify-start gap-2.5 font-normal flex-nowrap"
    >
      <span class="w-4 h-4 flex-none text-gray-500">
        <SettingsGearIcon />
      </span>
      {#if model_name}
        <!-- Model · provider truncate together as one line. -->
        <span class="truncate min-w-0 text-sm">
          <span class="font-medium">{model_name}</span>
          {#if provider}
            <span class="mx-1.5 text-gray-500" aria-hidden="true">·</span>
            <span class="font-normal text-gray-500">{provider}</span>
          {/if}
        </span>
      {:else}
        <span class="text-xs italic text-gray-500">Missing model selection</span
        >
      {/if}
    </button>
  </div>
</div>

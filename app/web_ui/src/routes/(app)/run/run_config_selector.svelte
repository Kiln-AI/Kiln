<script lang="ts">
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let selected_run_config: string | null = null
  export let onConfigChange: (config: string | null) => void

  let dropdown_open: boolean = false
  let selectedElement: HTMLElement
  let dropdownElement: HTMLElement

  // Create select options with section headers
  const quick_start_options: OptionGroup[] = [
    {
      label: "Task Default",
      options: [{ value: "default", label: "Run options 2" }],
    },
    {
      label: "Saved Configurations",
      options: [
        { value: "saved_config1", label: "Run options 1" },
        { value: "saved_config3", label: "Run options 3" },
      ],
    },
  ]

  // Helper to check if we're in read-only mode
  $: is_read_only = selected_run_config !== null

  function getConfigDisplayName(): string {
    if (!selected_run_config) return "Select an option"

    if (selected_run_config === "default") {
      return "Task Default: Run options 2"
    }

    // Find the saved config name from the options
    for (const group of quick_start_options) {
      for (const option of group.options) {
        if (option.value === selected_run_config) {
          return `Saved Configurations: ${option.label}`
        }
      }
    }
    return "Saved Configuration"
  }

  // Handle click outside to close dropdown
  function handleDocumentClick(event: MouseEvent) {
    if (
      dropdown_open &&
      selectedElement &&
      !selectedElement.contains(event.target as Node) &&
      dropdownElement &&
      !dropdownElement.contains(event.target as Node)
    ) {
      dropdown_open = false
    }
  }

  // Add/remove event listener when dropdown state changes
  $: if (dropdown_open) {
    document.addEventListener("click", handleDocumentClick)
  } else {
    document.removeEventListener("click", handleDocumentClick)
  }

  function handleClearSelection() {
    onConfigChange(null)
    dropdown_open = false
  }

  function handleOptionSelect(optionValue: unknown) {
    onConfigChange(optionValue as string)
    dropdown_open = false
  }
</script>

<div class="flex flex-col gap-2">
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="text-sm font-medium">Quick Select</span>
      <div class="text-gray-500">
        <InfoTooltip
          tooltip_text="Select a saved configuration to override the current options."
        />
      </div>
    </div>
  </div>

  <!-- Custom dropdown with clear button inside -->
  <div class="dropdown w-full relative">
    <div
      tabindex="0"
      role="listbox"
      class="select select-bordered w-full flex items-center cursor-pointer"
      bind:this={selectedElement}
      on:click={() => {
        dropdown_open = !dropdown_open
      }}
      on:keydown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          dropdown_open = !dropdown_open
        }
      }}
    >
      <span class="truncate flex-1">
        {getConfigDisplayName()}
      </span>
    </div>

    {#if dropdown_open}
      <div
        bind:this={dropdownElement}
        class="bg-base-100 rounded-box z-[1000] p-2 shadow border flex flex-col fixed mt-1"
        style="width: {selectedElement?.offsetWidth || 0}px;"
      >
        <!-- Clear button at the top -->
        {#if is_read_only}
          <div class="p-2 border-b border-base-200">
            <button
              class="pointer-events-auto w-full text-left px-2 py-1 hover:bg-base-200 rounded text-sm flex items-center"
              on:click={handleClearSelection}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="mr-2"
              >
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
              Clear Selection
            </button>
          </div>
        {/if}

        <!-- Options -->
        <ul class="menu overflow-y-auto flex-1">
          {#each quick_start_options as option_group}
            {#if option_group.label}
              <li class="menu-title pl-1">
                {#if option_group.label === "Task Default"}
                  <div class="flex items-center gap-2">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    >
                      <circle cx="12" cy="12" r="3"></circle>
                      <path
                        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1 1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
                      ></path>
                    </svg>
                    {option_group.label}
                  </div>
                {:else}
                  {option_group.label}
                {/if}
              </li>
            {/if}
            {#each option_group.options as option}
              <li>
                <button
                  class="pointer-events-auto {selected_run_config ===
                  option.value
                    ? 'active'
                    : ''}"
                  on:click={() => handleOptionSelect(option.value)}
                >
                  {option.label}
                </button>
              </li>
            {/each}
          {/each}
        </ul>
      </div>
    {/if}
  </div>
</div>

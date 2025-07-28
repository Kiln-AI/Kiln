<script lang="ts">
  import { onMount } from "svelte"
  import { get_provider_image } from "$lib/ui/provider_image"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { ModelProviderName } from "$lib/types"
  import AppPage from "../app_page.svelte"
  import {
    load_available_models,
    provider_name_from_id,
  } from "../../../lib/stores"
  import {
    checkProviderConnection,
    type ProviderSettings,
  } from "../../../lib/utils/provider_utils"
  import { goto } from "$app/navigation"
  import { client } from "../../../lib/api_client"
  import { createKilnError, KilnError } from "../../../lib/utils/error_handlers"

  interface Provider {
    name: ModelProviderName
    model_id: string
    supports_data_gen: boolean
    supports_logprobs: boolean
    supports_structured_output: boolean
    suggested_for_data_gen: boolean
    suggested_for_evals: boolean
    suggested_for_uncensored_data_gen: boolean
    uncensored: boolean
    untested_model: boolean
    structured_output_mode: string
    reasoning_capable: boolean
  }

  interface Model {
    family: string
    friendly_name: string
    name: string
    providers: Provider[]
  }

  interface ConfigData {
    model_list: Model[]
  }

  let models: Model[] = []
  let filteredModels: Model[] = []
  let loading = true
  let error: KilnError | null = null
  let providerSettings: ProviderSettings | null = null

  // Search and filter state
  let searchQuery = ""
  let selectedFamily = ""
  let selectedProvider = ""
  let selectedCapability = ""

  // Sorting state
  let sortBy = ""
  let sortDirection = "asc"

  // Available filter options
  let families: string[] = []
  let providers: string[] = []
  let capabilities = [
    { value: "data_gen", label: "Data Generation" },
    { value: "evals", label: "Evaluations" },
    { value: "structured_output", label: "Structured Output" },
    { value: "logprobs", label: "Logprobs" },
    { value: "uncensored", label: "Uncensored" },
  ]

  // Sort options
  let sortOptions = [
    { value: "name", label: "Name" },
    { value: "family", label: "Family" },
  ]

  // Convert arrays to OptionGroup format for fancy_select
  $: familyOptions = [
    {
      options: [
        { label: "All Families", value: "" },
        ...families.map((family) => ({
          label: family,
          value: family,
        })),
      ],
    },
  ]

  $: providerOptions = [
    {
      options: [
        { label: "All Providers", value: "" },
        ...providers.map((provider) => ({
          label: provider_name_from_id(provider),
          value: provider,
        })),
      ],
    },
  ]

  $: capabilityOptions = [
    {
      options: [
        { label: "All Capabilities", value: "" },
        ...capabilities.map((capability) => ({
          label: capability.label,
          value: capability.value,
        })),
      ],
    },
  ]

  // Active filters for badges
  $: activeFilters = [
    ...(selectedFamily
      ? [{ type: "family", value: selectedFamily, label: selectedFamily }]
      : []),
    ...(selectedProvider
      ? [
          {
            type: "provider",
            value: selectedProvider,
            label: provider_name_from_id(selectedProvider),
          },
        ]
      : []),
    ...(selectedCapability
      ? [
          {
            type: "capability",
            value: selectedCapability,
            label:
              capabilities.find((c) => c.value === selectedCapability)?.label ||
              selectedCapability,
          },
        ]
      : []),
  ]

  // Remove filter function
  function removeFilter(type: string) {
    switch (type) {
      case "family":
        selectedFamily = ""
        break
      case "provider":
        selectedProvider = ""
        break
      case "capability":
        selectedCapability = ""
        break
    }
  }

  async function fetchModelsFromRemoteConfig() {
    try {
      loading = true
      error = null

      const response = await fetch(
        "https://remote-config.getkiln.ai/kiln_config.json",
      )
      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.status}`)
      }

      const data: ConfigData = await response.json()
      models = data.model_list

      // Extract unique families and providers for filters
      families = [...new Set(models.map((m) => m.family))].sort()
      providers = [
        ...new Set(models.flatMap((m) => m.providers.map((p) => p.name))),
      ].sort()

      applyFilters()
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function load_provider_settings() {
    try {
      const { data: settings, error: load_settings_error } =
        await client.GET("/api/settings")
      if (load_settings_error) {
        throw load_settings_error
      }
      providerSettings = settings
    } catch (e) {
      console.error("Error loading provider settings", e)
    }
  }

  // Apply search and filters
  function applyFilters() {
    filteredModels = models.filter((model) => {
      // Text search
      const searchLower = searchQuery?.toLowerCase() || ""
      const matchesSearch =
        searchQuery === "" ||
        model.family?.toLowerCase().includes(searchLower) ||
        model.friendly_name?.toLowerCase().includes(searchLower) ||
        model.name?.toLowerCase().includes(searchLower) ||
        model.providers.some((p) =>
          p.model_id?.toLowerCase().includes(searchLower),
        )

      // Family filter
      const matchesFamily =
        selectedFamily === "" || model.family === selectedFamily

      // Provider filter
      const matchesProvider =
        selectedProvider === "" ||
        model.providers.some((p) => p.name === selectedProvider)

      // Capability filter
      let matchesCapability = true
      if (selectedCapability) {
        matchesCapability = model.providers.some((p) => {
          switch (selectedCapability) {
            case "data_gen":
              return p.supports_data_gen
            case "evals":
              return p.suggested_for_evals
            case "structured_output":
              return p.supports_structured_output
            case "logprobs":
              return p.supports_logprobs
            case "uncensored":
              return p.uncensored
            default:
              return true
          }
        })
      }

      return (
        matchesSearch && matchesFamily && matchesProvider && matchesCapability
      )
    })

    // Apply sorting
    applySorting()
  }

  // Apply sorting to filtered models
  function applySorting() {
    if (!sortBy) {
      return // No sorting applied
    }

    filteredModels = filteredModels.toSorted((a, b) => {
      let aValue: string
      let bValue: string

      switch (sortBy) {
        case "name":
          aValue = a.friendly_name.toLowerCase()
          bValue = b.friendly_name.toLowerCase()
          break
        case "family":
          aValue = a.family.toLowerCase()
          bValue = b.family.toLowerCase()
          break
        default:
          return 0
      }

      if (sortDirection === "asc") {
        return aValue.localeCompare(bValue)
      } else {
        return bValue.localeCompare(aValue)
      }
    })
  }

  // Clear all filters
  function clearFilters() {
    searchQuery = ""
    selectedFamily = ""
    selectedProvider = ""
    selectedCapability = ""
    sortBy = ""
    sortDirection = "asc"
    applyFilters()
  }

  // Toggle sort for a specific field
  function toggleSort(field: string) {
    if (sortBy === field) {
      if (sortDirection === "asc") {
        sortDirection = "desc"
      } else {
        // Remove sorting
        sortBy = ""
        sortDirection = "asc"
      }
    } else {
      sortBy = field
      sortDirection = "asc"
    }
    applySorting()
  }

  // Check if any filters are active
  $: hasActiveFilters =
    searchQuery ||
    selectedFamily ||
    selectedProvider ||
    selectedCapability ||
    sortBy

  // Get capability badges for a model
  function getCapabilityBadges(providers: Provider[]) {
    const badges = []

    if (providers.some((p) => p.supports_data_gen)) {
      badges.push({
        text: "Data Gen ★",
        color: "bg-blue-100 text-blue-800",
        tooltip:
          "Recommended for Synthetic Data Generation - one of the best models.",
      })
    }
    if (providers.some((p) => p.suggested_for_evals)) {
      badges.push({
        text: "Evals ★",
        color: "bg-green-100 text-green-800",
        tooltip: "Recommended for Evaluations - one of the best models.",
      })
    }
    if (providers.some((p) => p.suggested_for_uncensored_data_gen)) {
      badges.push({
        text: "Uncensored ★",
        color: "bg-red-100 text-red-800",
        tooltip:
          "Recommended for Uncensored Data Generation - one of the best models for evals where safeguards get in the way.",
      })
    }
    if (providers.some((p) => p.supports_structured_output)) {
      badges.push({
        text: "Structured",
        color: "bg-purple-100 text-purple-800",
        tooltip:
          "Supported structured output (JSON) preferring the tool-calling method.",
      })
    }
    if (providers.some((p) => p.supports_logprobs)) {
      badges.push({
        text: "Logprobs",
        color: "bg-orange-100 text-orange-800",
        tooltip:
          "Supports logprobs, a feature needed for the advanced eval method G-Eval",
      })
    }
    if (providers.some((p) => p.uncensored)) {
      badges.push({
        text: "Uncensored",
        color: "bg-red-100 text-red-800",
        tooltip:
          "Uncensored model which will produce any outputs (biased, malicious). Useful for adversarial evals.",
      })
    }

    return badges
  }

  // Watch for filter changes
  $: searchQuery,
    selectedFamily,
    selectedProvider,
    selectedCapability,
    models,
    applyFilters()

  // Watch for sort changes
  $: sortBy, sortDirection, applySorting()

  onMount(async () => {
    // we need to seed the available models in the Svelte store, because we get
    // the provider friendly name formatter from there, but we load the actual
    // model list from the remote config, because that is the most up to date
    await load_available_models()
    await fetchModelsFromRemoteConfig()
    // Load provider connection status for displaying connection indicators
    await load_provider_settings()
  })

  // Handle clicking on disconnected providers
  function handle_provider_click(provider_name: string) {
    const isConnected = providerSettings
      ? checkProviderConnection(provider_name, providerSettings)
      : true
    if (!isConnected) {
      goto("/settings/providers")
    }
  }
</script>

<svelte:head>
  <title>Models - Kiln</title>
</svelte:head>

<div class="max-w-[1400px]">
  <AppPage
    title="Model Library"
    subtitle="Browse available models"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.getkiln.ai/docs/models-and-ai-providers"
  >
    <!-- Loading State -->
    {#if loading}
      <div class="flex items-center justify-center py-12">
        <div class="text-center">
          <div
            class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"
          ></div>
          <p class="mt-4 text-gray-600">Loading models...</p>
        </div>
      </div>
    {:else if error}
      <!-- Error State -->
      <div class="bg-red-50 border border-red-200 rounded-md p-4">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg
              class="h-5 w-5 text-red-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-red-800">
              Error loading models
            </h3>
            <div class="mt-2 text-sm text-red-700">
              <p>{error.message}</p>
            </div>
            <div class="mt-4">
              <button
                on:click={fetchModelsFromRemoteConfig}
                class="bg-red-100 text-red-800 px-3 py-2 rounded-md text-sm font-medium hover:bg-red-200"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      </div>
    {:else}
      <!-- Search Bar -->
      <div class="mb-8">
        <label for="search" class="block text-sm font-medium text-gray-700 mb-3"
          >Search Models</label
        >
        <div class="relative">
          <div
            class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none"
          >
            <svg
              class="h-5 w-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <input
            id="search"
            type="text"
            bind:value={searchQuery}
            placeholder="Search by family, name, or model ID..."
            class="block w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
          />
        </div>
      </div>

      <!-- Filters Row -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <!-- Family Filter -->
        <div>
          <label
            for="family"
            class="block text-sm font-medium text-gray-700 mb-2">Family</label
          >
          <FancySelect
            bind:selected={selectedFamily}
            options={familyOptions}
            empty_label="All Families"
          />
        </div>

        <!-- Provider Filter -->
        <div>
          <label
            for="provider"
            class="block text-sm font-medium text-gray-700 mb-2">Provider</label
          >
          <FancySelect
            bind:selected={selectedProvider}
            options={providerOptions}
            empty_label="All Providers"
          />
        </div>

        <!-- Capability Filter -->
        <div>
          <label
            for="capability"
            class="block text-sm font-medium text-gray-700 mb-2"
            >Capability</label
          >
          <FancySelect
            bind:selected={selectedCapability}
            options={capabilityOptions}
            empty_label="All Capabilities"
          />
        </div>
      </div>

      <!-- Active Filters Badges -->
      {#if activeFilters.length > 0}
        <div class="mb-6">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-sm text-gray-500">Active filters:</span>
            {#each activeFilters as filter}
              <button
                on:click={() => removeFilter(filter.type)}
                class="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
              >
                {filter.label}
                <svg
                  class="ml-1.5 h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Results Count -->
      <div class="text-sm text-gray-500 mb-6">
        Showing {filteredModels.length} of {models.length} models
      </div>

      <!-- Action Bar (Clear Filters + Sorting) -->
      <div class="flex items-center justify-between mb-6">
        <!-- Clear Filters Button -->
        {#if hasActiveFilters}
          <button
            on:click={clearFilters}
            class="inline-flex items-center px-3 py-2 text-sm leading-4 font-medium rounded-md text-gray-700 bg-gray-100 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
            title="Clear all filters and sorting"
          >
            <svg
              class="h-4 w-4 mr-2"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
            Clear Filters
          </button>
        {:else}
          <div></div>
        {/if}

        <!-- Sorting Controls -->
        <div class="flex items-center space-x-2">
          <span class="text-sm text-gray-500">Sort by:</span>

          <!-- Sort Options -->
          <div class="flex items-center space-x-1">
            {#each sortOptions as option}
              <button
                on:click={() => toggleSort(option.value)}
                class="inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md transition-colors {sortBy ===
                option.value
                  ? 'text-gray-700 bg-gray-100 hover:bg-gray-200'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 border border-transparent'}"
              >
                {option.label}
                {#if sortBy === option.value}
                  <svg
                    class="ml-1 h-4 w-4 {sortDirection === 'desc'
                      ? 'rotate-180'
                      : ''}"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M5 15l7-7 7 7"
                    />
                  </svg>
                {/if}
              </button>
            {/each}
          </div>
        </div>
      </div>

      <!-- Models Grid -->
      {#if filteredModels.length === 0}
        <div class="text-center py-12">
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="mx-auto h-12 w-12"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M19.5617 7C19.7904 5.69523 18.7863 4.5 17.4617 4.5H6.53788C5.21323 4.5 4.20922 5.69523 4.43784 7"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M17.4999 4.5C17.5283 4.24092 17.5425 4.11135 17.5427 4.00435C17.545 2.98072 16.7739 2.12064 15.7561 2.01142C15.6497 2 15.5194 2 15.2588 2H8.74099C8.48035 2 8.35002 2 8.24362 2.01142C7.22584 2.12064 6.45481 2.98072 6.45704 4.00434C6.45727 4.11135 6.47146 4.2409 6.49983 4.5"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M15 18H9"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M2.38351 13.793C1.93748 10.6294 1.71447 9.04765 2.66232 8.02383C3.61017 7 5.29758 7 8.67239 7H15.3276C18.7024 7 20.3898 7 21.3377 8.02383C22.2855 9.04765 22.0625 10.6294 21.6165 13.793L21.1935 16.793C20.8437 19.2739 20.6689 20.5143 19.7717 21.2572C18.8745 22 17.5512 22 14.9046 22H9.09536C6.44881 22 5.12553 22 4.22834 21.2572C3.33115 20.5143 3.15626 19.2739 2.80648 16.793L2.38351 13.793Z"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
          <h3 class="mt-2 text-sm font-medium text-gray-900">
            No models found
          </h3>
          <p class="mt-1 text-sm text-gray-500">
            Try adjusting your search or filter criteria.
          </p>
        </div>
      {:else}
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {#each filteredModels as model}
            <div class="bg-white rounded-lg border">
              <!-- Model Header -->
              <div class="p-6 border-b border-gray-100">
                <div class="flex items-start justify-between">
                  <div class="flex-1">
                    <h3 class="text-lg font-semibold text-gray-900 break-all">
                      {model.friendly_name}
                    </h3>
                  </div>
                </div>
              </div>

              <!-- Capability Badges -->
              <div class="p-6 pt-4">
                <div class="flex flex-wrap gap-2 mb-4">
                  {#each getCapabilityBadges(model.providers) as badge}
                    <span
                      class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium tooltip tooltip-top before:z-50 before:whitespace-normal {badge.color}"
                      data-tip={badge.tooltip}
                    >
                      {badge.text}
                    </span>
                  {/each}
                </div>

                <!-- Providers -->
                <div>
                  <h4 class="text-sm font-medium text-gray-700 mb-3">
                    Available Providers
                  </h4>
                  <div class="space-y-2">
                    {#each model.providers as provider}
                      {@const isConnected = providerSettings
                        ? checkProviderConnection(
                            provider.name,
                            providerSettings,
                          )
                        : true}

                      <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                      <div
                        class="flex items-center justify-between p-3 bg-gray-50 rounded-md {!isConnected
                          ? 'opacity-50 cursor-pointer hover:opacity-60 transition-all'
                          : ''}"
                        on:click={!isConnected
                          ? () => handle_provider_click(provider.name)
                          : undefined}
                        on:keydown={!isConnected
                          ? (e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault()
                                handle_provider_click(provider.name)
                              }
                            }
                          : undefined}
                        role={!isConnected ? "button" : undefined}
                        tabindex={!isConnected ? 0 : -1}
                      >
                        <div class="flex items-center space-x-3">
                          <img
                            src={get_provider_image(provider.name)}
                            alt={provider.name}
                            class="w-6 h-6 rounded {!isConnected
                              ? 'grayscale'
                              : ''}"
                            on:error={(e) => {
                              if (e.target instanceof HTMLImageElement) {
                                e.target.style.display = "none"
                              }
                            }}
                          />
                          <div>
                            <p
                              class="text-sm font-medium {isConnected
                                ? 'text-gray-900'
                                : 'text-gray-600'}"
                            >
                              {provider_name_from_id(provider.name)}
                            </p>
                            <p
                              class="text-xs {isConnected
                                ? 'text-gray-500'
                                : 'text-gray-400'} break-all"
                            >
                              {provider.model_id}
                            </p>
                          </div>
                        </div>
                        <div class="flex items-center space-x-1">
                          {#if provider.supports_structured_output}
                            <span
                              class="w-2 h-2 bg-green-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                              data-tip="Supports Structured Output"
                            ></span>
                          {/if}
                          {#if provider.supports_logprobs}
                            <span
                              class="w-2 h-2 bg-blue-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                              data-tip="Supports Logprobs"
                            ></span>
                          {/if}
                          {#if provider.uncensored}
                            <span
                              class="w-2 h-2 bg-red-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                              data-tip="Uncensored Model"
                            ></span>
                          {/if}
                        </div>
                      </div>
                    {/each}
                  </div>
                </div>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  </AppPage>
</div>

<script lang="ts">
  import { onMount } from "svelte"
  import { get_provider_image } from "$lib/ui/provider_image"
  import FancySelect from "$lib/ui/fancy_select.svelte"
  import type { ModelProviderName, Task } from "$lib/types"
  import AppPage from "../app_page.svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import CreateNewRunConfigDialog from "$lib/ui/run_config_component/create_new_run_config_dialog.svelte"
  import {
    available_models,
    load_available_models,
    load_task,
    provider_name_from_id,
    ui_state,
  } from "$lib/stores"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { goto } from "$app/navigation"
  import { fetchPricingData, getModelPrice } from "./price"

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id

  const CAPABILITY_TOOLTIP_MESSAGES = {
    suggested_for_data_gen:
      "Recommended for Synthetic Data Generation - one of the best models.",
    suggested_for_evals:
      "Recommended for Evaluations - one of the best models.",
    suggested_for_uncensored_data_gen:
      "Recommended for Uncensored Data Generation - one of the best models for adversarial evals that require any outputs.",
    supports_finetuning:
      "Supports finetuning, to train the model on your own use cases.",
    supports_data_gen: "Supports Synthetic Data Generation.",
    supports_structured_output: "Supports structured output (JSON).",
    supports_logprobs:
      "Supports logprobs, a feature needed for the advanced eval method G-Eval.",
    supports_function_calling:
      "Supports function calling and tool use for enhanced capabilities.",
    uncensored:
      "Uncensored model which will produce any outputs (biased, malicious). Useful for adversarial evals.",
    reasoning_capable:
      "Best suited for tasks that require multi-step reasoning or complex decision-making.",
    supports_doc_extraction:
      "Supports document extraction, used for RAG (Retrieval-Augmented Generation).",
    supports_vision: "Supports vision inputs (image, video).",
  }

  interface Provider {
    name: ModelProviderName
    model_id: string | null
    provider_finetune_id: string | null
    supports_data_gen: boolean
    supports_logprobs: boolean
    supports_structured_output: boolean
    supports_function_calling: boolean
    suggested_for_data_gen: boolean
    suggested_for_evals: boolean
    suggested_for_uncensored_data_gen: boolean
    supports_vision: boolean
    supports_doc_extraction: boolean
    uncensored: boolean
    untested_model: boolean
    structured_output_mode: string
    reasoning_capable: boolean
    multimodal_mime_types: string[] | null
  }

  interface Model {
    family: string
    friendly_name: string
    name: string
    providers: Provider[]
    featured_rank?: number | null
    editorial_notes?: string | null
  }

  interface ConfigData {
    model_list: Model[]
  }

  let models: Model[] = []
  let filteredModels: Model[] = []
  let loading = true
  let pricingLoading = true
  let error: KilnError | null = null

  // Search and filter state
  let searchQuery = ""
  let selectedProvider = ""
  let selectedCapability = "featured"

  // Sorting state
  let sortBy = ""
  let sortDirection = "asc"

  // Available filter options
  let providers: string[] = []
  let capabilities = [
    { value: "featured", label: "Featured" },
    { value: "data_gen", label: "Data Generation" },
    { value: "structured_output", label: "Structured Output" },
    { value: "logprobs", label: "Logprobs" },
    { value: "tools", label: "Tools" },
    { value: "uncensored", label: "Uncensored" },
    { value: "finetune", label: "Finetune" },
    { value: "doc_extraction", label: "Doc Extraction (RAG)" },
    { value: "vision", label: "Vision" },
    { value: "reasoning_capable", label: "Reasoning" },
    { value: "suggested_for_evals", label: "Suggested for Evals" },
  ]

  // Sort options
  let sortOptions = [{ value: "name", label: "Name" }]

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
      case "provider":
        selectedProvider = ""
        break
      case "capability":
        selectedCapability = ""
        break
    }
  }

  async function fetchModelsFromRemoteConfig() {
    const response = await fetch(
      "https://remote-config.getkiln.ai/kiln_config_v2.json",
    )
    if (!response.ok) {
      throw new Error(`Failed to fetch models: ${response.status}`)
    }

    const data: ConfigData = await response.json()
    models = data.model_list

    // Extract unique providers for filters
    providers = [
      ...new Set(models.flatMap((m) => m.providers.map((p) => p.name))),
    ].sort()

    applyFilters()
  }

  async function loadPricing() {
    pricingLoading = true
    await fetchPricingData()
    pricingLoading = false
  }

  // Apply search and filters
  function applyFilters() {
    filteredModels = models.filter((model) => {
      // Text search
      const searchLower = searchQuery?.toLowerCase() || ""
      const matchesSearch =
        searchQuery === "" ||
        model.friendly_name?.toLowerCase().includes(searchLower) ||
        model.name?.toLowerCase().includes(searchLower) ||
        model.providers.some((p) =>
          p.model_id?.toLowerCase().includes(searchLower),
        )

      // Provider filter
      const matchesProvider =
        selectedProvider === "" ||
        model.providers.some((p) => p.name === selectedProvider)

      // Capability filter
      let matchesCapability = true
      if (selectedCapability === "featured") {
        matchesCapability = model.featured_rank != null
      } else if (selectedCapability) {
        matchesCapability = model.providers.some((p) => {
          switch (selectedCapability) {
            case "data_gen":
              return p.supports_data_gen
            case "suggested_for_evals":
              return p.suggested_for_evals
            case "structured_output":
              return p.supports_structured_output
            case "logprobs":
              return p.supports_logprobs
            case "tools":
              return p.supports_function_calling
            case "doc_extraction":
              return p.supports_doc_extraction
            case "uncensored":
              return p.uncensored
            case "finetune":
              return !!p.provider_finetune_id
            case "reasoning_capable":
              return p.reasoning_capable
            case "vision":
              return p.supports_vision
            default:
              return true
          }
        })
      }

      return matchesSearch && matchesProvider && matchesCapability
    })

    // Apply sorting
    applySorting()
  }

  // Apply sorting to filtered models
  function applySorting() {
    if (selectedCapability === "featured") {
      filteredModels = filteredModels.toSorted((a, b) => {
        const aRank = a.featured_rank ?? Number.MAX_SAFE_INTEGER
        const bRank = b.featured_rank ?? Number.MAX_SAFE_INTEGER
        return aRank - bRank
      })
      return
    }

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
    searchQuery || selectedProvider || selectedCapability || sortBy

  function getCapabilityBadges(providers: Provider[]) {
    // some badges are more important than others, so we display them first
    const leading_badges = []
    const trailing_badges = []

    if (providers.some((p) => !!p.provider_finetune_id)) {
      leading_badges.push({
        text: "Finetune ★",
        color: "bg-purple-100 text-purple-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_finetuning,
      })
    }
    if (providers.some((p) => p.suggested_for_data_gen)) {
      leading_badges.push({
        text: "Data Gen ★",
        color: "bg-blue-100 text-blue-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.suggested_for_data_gen,
      })
    } else if (providers.some((p) => p.supports_data_gen)) {
      trailing_badges.push({
        text: "Data Gen",
        color: "bg-blue-100 text-blue-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_data_gen,
      })
    }

    if (providers.some((p) => p.suggested_for_evals)) {
      leading_badges.push({
        text: "Evals ★",
        color: "bg-green-100 text-green-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.suggested_for_evals,
      })
    }

    if (providers.some((p) => p.suggested_for_uncensored_data_gen)) {
      leading_badges.push({
        text: "Uncensored ★",
        color: "bg-red-100 text-red-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.suggested_for_uncensored_data_gen,
      })
    } else if (providers.some((p) => p.uncensored)) {
      trailing_badges.push({
        text: "Uncensored",
        color: "bg-red-100 text-red-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.uncensored,
      })
    }

    if (providers.some((p) => p.reasoning_capable)) {
      trailing_badges.push({
        text: "Reasoning",
        color: "bg-lime-100 text-lime-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.reasoning_capable,
      })
    }
    if (providers.some((p) => p.supports_structured_output)) {
      trailing_badges.push({
        text: "Structured Output",
        color: "bg-teal-100 text-teal-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_structured_output,
      })
    }
    if (providers.some((p) => p.supports_function_calling)) {
      trailing_badges.push({
        text: "Tools",
        color: "bg-indigo-100 text-indigo-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_function_calling,
      })
    }
    if (providers.some((p) => p.supports_logprobs)) {
      trailing_badges.push({
        text: "Logprobs",
        color: "bg-orange-100 text-orange-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_logprobs,
      })
    }
    if (providers.some((p) => p.supports_doc_extraction)) {
      trailing_badges.push({
        text: "Doc Extraction",
        color: "bg-amber-100 text-amber-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_doc_extraction,
      })
    }
    if (providers.some((p) => p.supports_vision)) {
      trailing_badges.push({
        text: "Vision",
        color: "bg-pink-100 text-pink-800",
        tooltip: CAPABILITY_TOOLTIP_MESSAGES.supports_vision,
      })
    }

    return [...leading_badges, ...trailing_badges]
  }

  // Watch for filter changes
  $: void (searchQuery,
  selectedProvider,
  selectedCapability,
  models,
  applyFilters())

  // Watch for sort changes
  $: void (sortBy, sortDirection, applySorting())

  onMount(async () => {
    try {
      loading = true
      error = null

      loadPricing()

      if (project_id && task_id) {
        task = await load_task(project_id, task_id)
      }

      if (!task) {
        throw new Error("Task not found")
      }

      await load_available_models()
      await fetchModelsFromRemoteConfig()
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  })

  function model_provider_is_connected(
    remote_provider_name: string,
    remote_model_name: string | null,
    remote_provider_model_id: string | null,
    remote_provider_finetune_id: string | null,
  ) {
    const provider = $available_models.find(
      (p) => p.provider_id === remote_provider_name,
    )
    if (!provider) {
      return false
    }

    // some models are only available for finetuning, they have a finetune_id but no model_id
    // so we consider the model connected if we have the provider connected
    if (!remote_provider_model_id && remote_provider_finetune_id) {
      return true
    }

    return provider.models.some((model) => model.id === remote_model_name)
  }

  // the user has at least one ollama model available, which means they have ollama connected (but not necessarily all models)
  $: ollama_is_connected = $available_models.some(
    (provider) => provider.provider_id === "ollama",
  )

  function get_ollama_model_href(model_id: string) {
    return "https://ollama.com/library/" + model_id
  }

  function model_not_connected_href(
    provider_id: string,
    model_id: string | null,
  ) {
    if (provider_id === "ollama" && ollama_is_connected && model_id) {
      return get_ollama_model_href(model_id)
    }
    return "/settings/providers"
  }

  function model_not_connected_tooltip(provider_id: string) {
    if (provider_id === "ollama" && ollama_is_connected) {
      return "Install the model in Ollama to use it"
    }
    return "Connect the provider to use this model"
  }

  function getModelPricing(model: Model) {
    const pricingProvider =
      model.providers.find((p) => p.name === "openrouter") || model.providers[0]
    if (!pricingProvider?.model_id) {
      return null
    }
    return getModelPrice(pricingProvider.name, pricingProvider.model_id)
  }

  let connect_provider_dialog: Dialog | null = null
  let connect_provider_model: Model | null = null

  let create_run_config_dialog: CreateNewRunConfigDialog | null = null
  let create_run_config_model_id: string | undefined = undefined
  let task: Task | null = null

  function findFirstConnectedProvider(model: Model): Provider | null {
    return (
      model.providers.find((p) =>
        model_provider_is_connected(
          p.name,
          model.name,
          p.model_id,
          p.provider_finetune_id,
        ),
      ) || null
    )
  }

  function handleKeyPress(event: KeyboardEvent, model: Model) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onClick(model)
    }
  }

  function onClick(model: Model, provider?: Provider) {
    const connectedProvider = provider || findFirstConnectedProvider(model)
    if (!connectedProvider) {
      connect_provider_model = model
      connect_provider_dialog?.show()
      return
    }
    create_run_config_model_id = `${connectedProvider.name}/${model.name}`
    create_run_config_dialog?.show()
  }

  function tryModel(model: Model) {
    const connectedProvider = findFirstConnectedProvider(model)
    if (!connectedProvider) {
      connect_provider_model = model
      connect_provider_dialog?.show()
      return
    }
    const urlParams = new URLSearchParams()
    urlParams.set("model", `${connectedProvider.name}/${model.name}`)
    goto(`/run?${urlParams.toString()}`)
  }
</script>

<svelte:head>
  <title>Models - Kiln</title>
</svelte:head>

<div class="max-w-[1400px] overflow-x-hidden">
  <AppPage
    title="Model Library"
    subtitle="Browse available models"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/models-and-ai-providers"
    breadcrumbs={project_id && task_id
      ? [
          {
            label: "Optimize",
            href: `/optimize/${project_id}/${task_id}`,
          },
        ]
      : []}
    action_buttons={[
      {
        label: "Manage Providers",
        href: "/settings/providers",
      },
    ]}
  >
    <!-- Loading State -->
    {#if loading || pricingLoading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
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
              <p>{error.getMessage()}</p>
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
      <div class="px-1">
        <!-- Search Bar -->
        <div class="mb-8">
          <label
            for="search"
            class="block text-sm font-medium text-gray-700 mb-3"
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
              placeholder="Search by name, model ID..."
              class="block w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
            />
          </div>
        </div>

        <!-- Filters Row -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <!-- Provider Filter -->
          <div>
            <label
              for="provider"
              class="block text-sm font-medium text-gray-700 mb-2"
              >Provider</label
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
              >Filter by Capability</label
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
              {@const prices = getModelPricing(model)}
              <div
                class="bg-white rounded-lg border border-base-300 shadow-md hover:shadow-lg hover:border-primary/50 transition-all duration-200 transform hover:-translate-y-1 hover:z-10"
                on:click={() => onClick(model)}
                on:keydown={(event) => handleKeyPress(event, model)}
                role="button"
                tabindex="0"
                aria-label={model.friendly_name}
              >
                <!-- Model Header -->
                <div class="p-6 border-b border-gray-100">
                  <div class="flex items-start justify-between">
                    <div class="flex-1">
                      <div
                        class="flex flex-row items-center justify-between gap-1"
                      >
                        <h3
                          class="text-lg font-semibold text-gray-900 break-all"
                        >
                          {model.friendly_name}
                        </h3>
                        <button
                          class="btn btn-xs"
                          tabindex="0"
                          on:click|stopPropagation={() => tryModel(model)}
                          on:keydown|stopPropagation={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault()
                              tryModel(model)
                            }
                          }}>Try</button
                        >
                      </div>
                      {#if model.editorial_notes}
                        <p class="text-sm text-gray-500 mt-1">
                          {model.editorial_notes}
                        </p>
                      {/if}
                    </div>
                  </div>
                </div>

                {#if prices && (prices.inputPrice !== null || prices.outputPrice !== null)}
                  <div
                    class="text-xs font-light text-gray-500 border-b border-gray-100 px-6 py-3 flex items-center justify-around"
                  >
                    {#if prices.inputPrice !== null}
                      <span>Input: ${prices.inputPrice.toFixed(2)}/M</span>
                    {/if}
                    {#if prices.outputPrice !== null}
                      <span>Output: ${prices.outputPrice.toFixed(2)}/M</span>
                    {/if}
                  </div>
                {/if}

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
                        {@const isConnected = model_provider_is_connected(
                          provider.name,
                          model.name,
                          provider.model_id,
                          provider.provider_finetune_id,
                        )}
                        <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                        <div
                          class="flex items-center justify-between p-3 bg-gray-50 rounded-md transition-all cursor-pointer hover:outline hover:outline-1 hover:outline-primary/50 {isConnected
                            ? ''
                            : 'opacity-50 hover:opacity-60'}"
                          on:click|stopPropagation={() => {
                            if (isConnected) onClick(model, provider)
                          }}
                          on:keydown|stopPropagation={(e) => {
                            if (
                              (e.key === "Enter" || e.key === " ") &&
                              isConnected
                            ) {
                              e.preventDefault()
                              onClick(model, provider)
                            }
                          }}
                          role="button"
                          tabindex="0"
                        >
                          {#if isConnected}
                            <div class="flex items-center space-x-3">
                              <img
                                src={get_provider_image(provider.name)}
                                alt={provider.name}
                                class="w-6 h-6 rounded"
                                on:error={(e) => {
                                  if (e.target instanceof HTMLImageElement) {
                                    e.target.style.display = "none"
                                  }
                                }}
                              />
                              <div>
                                <p class="text-sm font-medium text-gray-900">
                                  {provider_name_from_id(provider.name)}
                                </p>
                                <p class="text-xs text-gray-500 break-all">
                                  {provider.model_id ||
                                    `${provider.provider_finetune_id} (Finetune Only)`}
                                </p>
                              </div>
                            </div>
                          {:else}
                            <a
                              href={model_not_connected_href(
                                provider.name,
                                provider.model_id,
                              )}
                              class="text-left flex items-center space-x-3 transition-all cursor-pointer flex-1 tooltip tooltip-top before:z-50 before:whitespace-normal"
                              on:click|stopPropagation
                              data-tip={model_not_connected_tooltip(
                                provider.name,
                              )}
                            >
                              <img
                                src={get_provider_image(provider.name)}
                                alt={provider.name}
                                class="w-6 h-6 rounded"
                                on:error={(e) => {
                                  if (e.target instanceof HTMLImageElement) {
                                    e.target.style.display = "none"
                                  }
                                }}
                              />
                              <div>
                                <p class="text-sm font-medium text-gray-900">
                                  {provider_name_from_id(provider.name)}
                                </p>
                                <p class="text-xs text-gray-500 break-all">
                                  {provider.model_id}
                                </p>
                              </div>
                            </a>
                          {/if}
                          <div class="flex items-center space-x-1">
                            {#if provider.reasoning_capable}
                              <span
                                class="w-2 h-2 bg-lime-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.reasoning_capable}
                              ></span>
                            {/if}
                            {#if provider.provider_finetune_id}
                              <span
                                class="w-2 h-2 bg-purple-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.supports_finetuning}
                              ></span>
                            {/if}
                            {#if provider.supports_structured_output}
                              <span
                                class="w-2 h-2 bg-teal-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.supports_structured_output}
                              ></span>
                            {/if}
                            {#if provider.supports_function_calling}
                              <span
                                class="w-2 h-2 bg-indigo-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.supports_function_calling}
                              ></span>
                            {/if}
                            {#if provider.supports_doc_extraction}
                              <span
                                class="w-2 h-2 bg-amber-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.supports_doc_extraction}
                              ></span>
                            {/if}
                            {#if provider.supports_vision}
                              <span
                                class="w-2 h-2 bg-pink-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={// in practice, vision models should always have some mime types, if the fallback kicks in, the model definition is probably incorrect
                                provider.multimodal_mime_types &&
                                provider.multimodal_mime_types.length > 0
                                  ? provider.multimodal_mime_types.join(", ")
                                  : CAPABILITY_TOOLTIP_MESSAGES.supports_vision}
                              ></span>
                            {/if}
                            {#if provider.supports_logprobs}
                              <span
                                class="w-2 h-2 bg-orange-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.supports_logprobs}
                              ></span>
                            {/if}
                            {#if provider.uncensored}
                              <span
                                class="w-2 h-2 bg-red-400 rounded-full tooltip tooltip-top before:z-50 before:whitespace-normal"
                                data-tip={CAPABILITY_TOOLTIP_MESSAGES.uncensored}
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

          {#if selectedCapability === "featured"}
            <div class="flex justify-center mt-10">
              <button
                on:click={() => (selectedCapability = "")}
                class="btn btn-primary btn-lg"
              >
                See All {models.length} Models
              </button>
            </div>
          {/if}
        {/if}
      </div>
    {/if}
  </AppPage>
</div>

<Dialog
  bind:this={connect_provider_dialog}
  title="Connect to Provider"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Connect Provider",
      isPrimary: true,
      action: () => {
        goto("/settings/providers")
        return true
      },
    },
  ]}
>
  <div class="flex flex-col gap-4">
    <p class="text-sm text-gray-600">
      To use <span class="font-medium"
        >{connect_provider_model?.friendly_name ?? "this model"}</span
      >, please connect at least one of its providers.
    </p>
    {#if connect_provider_model}
      <div class="flex flex-col gap-2">
        <p class="text-sm font-medium text-gray-700">Available providers</p>
        {#each connect_provider_model.providers as provider}
          <div class="flex items-center gap-3 p-3 bg-gray-50 rounded-md">
            <img
              src={get_provider_image(provider.name)}
              alt={provider.name}
              class="w-6 h-6 rounded"
              on:error={(e) => {
                if (e.target instanceof HTMLImageElement) {
                  e.target.style.display = "none"
                }
              }}
            />
            <span class="text-sm text-gray-700"
              >{provider_name_from_id(provider.name)}</span
            >
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Dialog>

{#if task && project_id}
  <CreateNewRunConfigDialog
    bind:this={create_run_config_dialog}
    {project_id}
    {task}
    model={create_run_config_model_id}
    new_run_config_created={() => goto(`/optimize/${project_id}/${task_id}`)}
  />
{/if}

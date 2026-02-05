<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { provider_name_from_id } from "$lib/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import { getContext } from "svelte"
  import type { Writable } from "svelte/store"

  type ProviderInfo = {
    id: string
    name: string
    provider_type: "builtin" | "custom"
  }

  type UserModelEntry = {
    provider_type: "builtin" | "custom"
    provider_id: string
    model_id: string
    name?: string | null
    overrides?: Record<string, unknown> | null
  }

  let available_providers: ProviderInfo[] = []
  let user_models: UserModelEntry[] = []
  let loading = true
  let error: KilnError | null = null

  // Form state
  let new_model_provider: string | null = null
  let new_model_name: string | null = null
  let new_model_display_name: string | null = null
  let show_advanced = false

  // Override form state (Advanced section)
  let override_supports_structured_output: boolean | null = null
  let override_structured_output_mode: string | null = null
  let override_supports_data_gen: boolean | null = null
  let override_supports_logprobs: boolean | null = null
  let override_supports_function_calling: boolean | null = null
  let override_supports_vision: boolean | null = null
  let override_reasoning_capable: boolean | null = null
  let override_parser: string | null = null

  const load_data = async () => {
    try {
      loading = true

      // Load available providers
      const { data: providers, error: providers_error } = await client.GET(
        "/api/settings/available_providers",
      )
      if (providers_error) throw providers_error
      available_providers = providers || []

      // Load user models
      const { data: models, error: models_error } = await client.GET(
        "/api/settings/user_models",
      )
      if (models_error) throw models_error
      user_models = models || []

      if (available_providers.length > 0) {
        new_model_provider = available_providers[0].id
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  onMount(async () => {
    await load_data()
  })

  function build_overrides(): Record<string, unknown> | undefined {
    const overrides: Record<string, unknown> = {}

    if (override_supports_structured_output !== null) {
      overrides.supports_structured_output = override_supports_structured_output
    }
    if (override_structured_output_mode !== null) {
      overrides.structured_output_mode = override_structured_output_mode
    }
    if (override_supports_data_gen !== null) {
      overrides.supports_data_gen = override_supports_data_gen
    }
    if (override_supports_logprobs !== null) {
      overrides.supports_logprobs = override_supports_logprobs
    }
    if (override_supports_function_calling !== null) {
      overrides.supports_function_calling = override_supports_function_calling
    }
    if (override_supports_vision !== null) {
      overrides.supports_vision = override_supports_vision
    }
    if (override_reasoning_capable !== null) {
      overrides.reasoning_capable = override_reasoning_capable
    }
    if (override_parser !== null) {
      overrides.parser = override_parser
    }

    return Object.keys(overrides).length > 0 ? overrides : undefined
  }

  async function add_model() {
    if (!new_model_provider || !new_model_name) {
      throw new KilnError("Provider and model ID are required", null)
    }

    const provider = available_providers.find(
      (p) => p.id === new_model_provider,
    )
    if (!provider) {
      throw new KilnError("Provider not found", null)
    }

    const entry: UserModelEntry = {
      provider_type: provider.provider_type,
      provider_id: new_model_provider,
      model_id: new_model_name,
    }

    if (new_model_display_name) {
      entry.name = new_model_display_name
    }

    const overrides = build_overrides()
    if (overrides) {
      entry.overrides = overrides
    }

    const { error: add_error } = await client.POST(
      "/api/settings/user_models",
      {
        body: entry,
      },
    )
    if (add_error) throw add_error

    // Reset form
    new_model_name = null
    new_model_display_name = null
    reset_overrides()

    // Refresh list
    await load_data()

    return true
  }

  function reset_overrides() {
    override_supports_structured_output = null
    override_structured_output_mode = null
    override_supports_data_gen = null
    override_supports_logprobs = null
    override_supports_function_calling = null
    override_supports_vision = null
    override_reasoning_capable = null
    override_parser = null
    show_advanced = false
  }

  async function remove_model(model: UserModelEntry) {
    const { error: delete_error } = await client.DELETE(
      "/api/settings/user_models",
      {
        params: {
          query: {
            provider_type: model.provider_type,
            provider_id: model.provider_id,
            model_id: model.model_id,
          },
        },
      },
    )
    if (delete_error) throw delete_error

    // Refresh list
    await load_data()
  }

  function get_provider_display_name(model: UserModelEntry): string {
    if (model.provider_type === "custom") {
      return model.provider_id
    }
    return provider_name_from_id(model.provider_id)
  }

  function get_model_display_name(model: UserModelEntry): string {
    return model.name || model.model_id
  }

  function has_overrides(model: UserModelEntry): boolean {
    return (
      model.overrides !== undefined &&
      model.overrides !== null &&
      Object.keys(model.overrides).length > 0
    )
  }

  // You can get here 2 ways, build a breadcrumb for each
  const lastPageUrl = getContext<Writable<URL | undefined>>("lastPageUrl")
  function get_breadcrumbs() {
    const breadcrumbs = [{ label: "Settings", href: "/settings" }]

    if ($lastPageUrl && $lastPageUrl.pathname === "/settings/providers") {
      breadcrumbs.push({ label: "AI Providers", href: "/settings/providers" })
    }

    return breadcrumbs
  }

  let add_model_dialog: Dialog | null = null

  function show_add_model_modal() {
    add_model_dialog?.show()
  }
</script>

<AppPage
  title="Manage Custom Models"
  sub_subtitle="Add/remove additional models from your connected AI providers, on top of those already included with Kiln."
  breadcrumbs={get_breadcrumbs()}
  action_buttons={user_models && user_models.length > 0
    ? [
        {
          label: "Add Model",
          primary: true,
          handler: show_add_model_modal,
        },
      ]
    : []}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="alert alert-error">
        <span>{error.message}</span>
      </div>
    </div>
  {:else if user_models.length > 0}
    <div class="flex flex-col gap-4">
      {#each user_models as model}
        <div
          class="flex flex-row gap-2 card bg-base-200 py-2 px-4 items-center"
        >
          <div class="font-medium min-w-48">
            {get_provider_display_name(model)}
          </div>
          <div class="grow">
            {get_model_display_name(model)}
            {#if has_overrides(model)}
              <span class="badge badge-sm badge-info ml-2">Custom Settings</span
              >
            {/if}
          </div>
          <button
            on:click={() => remove_model(model)}
            class="link text-sm text-gray-500"
          >
            Remove
          </button>
        </div>
      {/each}
    </div>
  {:else}
    <div class="flex flex-col gap-4 justify-center items-center min-h-[30vh]">
      <button
        class="btn btn-wide btn-primary mt-4"
        on:click={show_add_model_modal}
      >
        Add Model
      </button>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={add_model_dialog}
  title="Add Model"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Add Model",
      asyncAction: add_model,
      disabled: !new_model_provider || !new_model_name,
      isPrimary: true,
    },
  ]}
>
  <div class="text-sm">Add a model from an existing provider.</div>
  <div class="text-sm text-gray-500 mt-3">
    Provide the exact model ID used by the provider API.
  </div>

  <div class="flex flex-col gap-4 mt-8">
    <FormElement
      label="Model Provider"
      id="model_provider"
      inputType="select"
      select_options={available_providers.map((p) => [p.id, p.name])}
      bind:value={new_model_provider}
    />

    <FormElement
      label="Model ID"
      id="model_id"
      inputType="input"
      placeholder="e.g., gpt-4o-mini or llama3"
      bind:value={new_model_name}
    />

    <FormElement
      label="Display Name (Optional)"
      id="display_name"
      inputType="input"
      placeholder="e.g., My Custom Model"
      bind:value={new_model_display_name}
    />

    <!-- Advanced Section -->
    <div class="collapse collapse-arrow bg-base-200">
      <input type="checkbox" bind:checked={show_advanced} />
      <div class="collapse-title font-medium">Advanced Options</div>
      <div class="collapse-content">
        <div class="flex flex-col gap-4 pt-2">
          <FormElement
            label="Supports Structured Output"
            id="supports_structured_output"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_supports_structured_output}
          />

          <FormElement
            label="Structured Output Mode"
            id="structured_output_mode"
            inputType="select"
            select_options={[
              ["", "Default (JSON Instructions)"],
              ["json_schema", "JSON Schema"],
              ["json_mode", "JSON Mode"],
              ["json_instructions", "JSON Instructions"],
            ]}
            bind:value={override_structured_output_mode}
          />

          <FormElement
            label="Supports Data Generation"
            id="supports_data_gen"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_supports_data_gen}
          />

          <FormElement
            label="Supports Logprobs"
            id="supports_logprobs"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_supports_logprobs}
          />

          <FormElement
            label="Supports Function Calling"
            id="supports_function_calling"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_supports_function_calling}
          />

          <FormElement
            label="Supports Vision"
            id="supports_vision"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_supports_vision}
          />

          <FormElement
            label="Reasoning Capable (Thinking Model)"
            id="reasoning_capable"
            inputType="select"
            select_options={[
              ["", "Default (No)"],
              ["true", "Yes"],
              ["false", "No"],
            ]}
            bind:value={override_reasoning_capable}
          />

          <FormElement
            label="Output Parser"
            id="parser"
            inputType="select"
            select_options={[
              ["", "None"],
              ["r1_thinking", "R1 Thinking (<think> tags)"],
            ]}
            bind:value={override_parser}
          />
        </div>
      </div>
    </div>
  </div>
</Dialog>

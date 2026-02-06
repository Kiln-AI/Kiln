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
  import TableButton from "../../../generate/[project_id]/[task_id]/table_button.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

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
  // Use "" for default/unset state so fancy_select shows the default option selected
  let override_supports_structured_output: string = ""
  let override_structured_output_mode: string = "json_schema"
  let override_supports_logprobs: string = ""
  let override_supports_function_calling: string = ""
  let override_supports_vision: string = ""
  let override_reasoning_capable: string = ""
  let override_parser: string = ""

  // Fancy select option groups for model settings
  const yes_no_default_options: OptionGroup[] = [
    {
      options: [
        { label: "Default (No)", value: "" },
        { label: "Yes", value: "true" },
        { label: "No", value: "false" },
      ],
    },
  ]

  const structured_output_options: OptionGroup[] = [
    {
      options: [
        {
          label: "Default (No)",
          value: "",
          description: "Model does not support structured output.",
        },
        {
          label: "Yes",
          value: "true",
          description: "Model supports structured JSON output.",
        },
        {
          label: "No",
          value: "false",
          description: "Model does not support structured output.",
        },
      ],
    },
  ]

  const structured_output_mode_options: OptionGroup[] = [
    {
      options: [
        {
          label: "JSON Schema",
          value: "json_schema",
          description:
            "Provider enforces output matches a JSON schema. Most reliable if supported.",
        },
        {
          label: "Function Calling (Strict)",
          value: "function_calling",
          description: "Request JSON using function calling capabilities.",
        },
        {
          label: "Function Calling (Weak)",
          value: "function_calling_weak",
          description:
            "Request JSON using function calling capabilities, but with weaker schema enforcement.",
        },
        {
          label: "JSON Mode",
          value: "json_mode",
          description:
            "Provider guarantees valid JSON, but not a specific schema.",
        },
        {
          label: "JSON Instructions + JSON Mode",
          value: "json_instruction_and_object",
          description:
            "Add prompt instructions for schema, plus API JSON mode for valid JSON.",
        },
        {
          label: "JSON Instructions",
          value: "json_instructions",
          description:
            "Add prompt instructions to request JSON matching the schema. No API capabilities are used.",
        },
        {
          label: "JSON Custom Instructions",
          value: "json_custom_instructions",
          description:
            "Model outputs JSON with custom instructions already in the system prompt. Don't append additional JSON instructions.",
        },
      ],
    },
  ]

  const parser_options: OptionGroup[] = [
    {
      options: [
        { label: "None", value: "" },
        {
          label: "R1 Thinking",
          value: "r1_thinking",
          description: "Parse <think> tags from reasoning models.",
        },
      ],
    },
  ]

  const reasoning_capable_options: OptionGroup[] = [
    {
      options: [
        { label: "Default (No)", value: "" },
        {
          label: "Yes",
          value: "true",
          description: "Reasoning should always be returned, fail if missing.",
        },
        {
          label: "No",
          value: "false",
          description: "Reasoning not expected or optional.",
        },
      ],
    },
  ]

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

    if (override_supports_structured_output !== "") {
      overrides.supports_structured_output =
        override_supports_structured_output === "true"
    }
    if (override_structured_output_mode !== "") {
      overrides.structured_output_mode = override_structured_output_mode
    }
    if (override_supports_logprobs !== "") {
      overrides.supports_logprobs = override_supports_logprobs === "true"
    }
    if (override_supports_function_calling !== "") {
      overrides.supports_function_calling =
        override_supports_function_calling === "true"
    }
    if (override_supports_vision !== "") {
      overrides.supports_vision = override_supports_vision === "true"
    }
    if (override_reasoning_capable !== "") {
      overrides.reasoning_capable = override_reasoning_capable === "true"
    }
    if (override_parser !== "") {
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
    override_supports_structured_output = ""
    override_structured_output_mode = ""
    override_supports_logprobs = ""
    override_supports_function_calling = ""
    override_supports_vision = ""
    override_reasoning_capable = ""
    override_parser = ""
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

  const override_labels: Record<string, string> = {
    supports_structured_output: "Structured Output",
    structured_output_mode: "Output Mode",
    supports_data_gen: "Data Generation",
    supports_logprobs: "Logprobs",
    supports_function_calling: "Function Calling",
    supports_vision: "Vision",
    reasoning_capable: "Reasoning",
    parser: "Parser",
  }

  function format_overrides(model: UserModelEntry): string {
    if (!model.overrides) return ""
    const items = Object.entries(model.overrides)
      .map(([key, value]) => {
        const label = override_labels[key] || key
        const displayValue =
          typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)
        return `**${label}**: ${displayValue}`
      })
      .join("\n")
    return items
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
  title="Custom Models"
  subtitle="Add models from your connected AI providers"
  sub_subtitle="Read the Docs"
  sub_subtitle_link="https://docs.kiln.tech/docs/models-and-ai-providers"
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
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Models</div>
      <div class="text-error text-sm">
        {error.message || "An unknown error occurred"}
      </div>
    </div>
  {:else if user_models.length > 0}
    <div class="rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th>Provider</th>
            <th>Model</th>
            <th>Settings</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each user_models as model}
            <tr>
              <td class="font-medium">{get_provider_display_name(model)}</td>
              <td>
                <div class="flex flex-col">
                  <span>{get_model_display_name(model)}</span>
                  {#if model.name && model.name !== model.model_id}
                    <span class="text-xs text-base-content/60"
                      >{model.model_id}</span
                    >
                  {/if}
                </div>
              </td>
              <td>
                {#if has_overrides(model)}
                  <span class="text-base-content/60">Custom</span>
                  <InfoTooltip
                    tooltip_text={format_overrides(model)}
                    no_pad={true}
                  />
                {:else}
                  <span class="text-base-content/60">Default</span>
                {/if}
              </td>
              <td class="p-0">
                <div class="dropdown dropdown-end dropdown-hover">
                  <TableButton />
                  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                  <ul
                    tabindex="0"
                    class="dropdown-content menu bg-base-100 rounded-box z-[1] w-40 p-2 shadow"
                  >
                    <li>
                      <button on:click={() => remove_model(model)}>
                        Remove Model
                      </button>
                    </li>
                  </ul>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="flex flex-col items-center justify-center min-h-[50vh]">
      <Intro
        title="Add Custom Models"
        description_paragraphs={[
          "Add models from your connected AI providers beyond those already included with Kiln.",
          "Custom models let you use the latest models or specialized variants from any connected provider.",
        ]}
        action_buttons={[
          {
            label: "Add Model",
            onClick: show_add_model_modal,
            is_primary: true,
          },
        ]}
      >
        <svelte:fragment slot="icon">
          <svg
            class="w-12 h-12"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M12 6V18M18 12H6"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
        </svelte:fragment>
      </Intro>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={add_model_dialog}
  title="Add Custom Model"
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
  <div class="flex flex-col gap-4">
    <FormElement
      label="Model Provider"
      id="model_provider"
      inputType="fancy_select"
      fancy_select_options={[
        {
          options: available_providers.map((p) => ({
            label: p.name,
            value: p.id,
          })),
        },
      ]}
      bind:value={new_model_provider}
    />

    <FormElement
      label="Model ID"
      id="model_id"
      inputType="input"
      placeholder="e.g., gpt-4o-mini or llama3"
      description="Must be the exact model ID used by the provider API."
      bind:value={new_model_name}
    />

    <FormElement
      label="Display Name"
      id="display_name"
      inputType="input"
      placeholder="e.g., My Custom Model"
      info_description="The name you'll see in Kiln dropdowns."
      optional={true}
      bind:value={new_model_display_name}
    />

    <!-- Model Settings Section -->
    <div class="collapse collapse-arrow bg-base-200">
      <input type="checkbox" bind:checked={show_advanced} />
      <div class="collapse-title font-medium">Model Settings</div>
      <div class="collapse-content">
        <div class="flex flex-col gap-4 pt-2">
          <FormElement
            label="Supports Structured Output"
            id="supports_structured_output"
            inputType="fancy_select"
            fancy_select_options={structured_output_options}
            info_description="Whether the model can return responses in a specific JSON format."
            bind:value={override_supports_structured_output}
          />

          <FormElement
            label="Structured Output Mode"
            id="structured_output_mode"
            inputType="fancy_select"
            fancy_select_options={structured_output_mode_options}
            info_description="JSON Schema typically works best on newer models. See API docs from the providers for the best mode."
            bind:value={override_structured_output_mode}
          />

          <FormElement
            label="Supports Logprobs"
            id="supports_logprobs"
            inputType="fancy_select"
            fancy_select_options={yes_no_default_options}
            info_description="Whether the model returns token log probabilities. Used for confidence scoring in evals."
            bind:value={override_supports_logprobs}
          />

          <FormElement
            label="Supports Function Calling"
            id="supports_function_calling"
            inputType="fancy_select"
            fancy_select_options={yes_no_default_options}
            info_description="Whether the model supports tool/function calling APIs for structured interactions."
            bind:value={override_supports_function_calling}
          />

          <FormElement
            label="Supports Vision"
            id="supports_vision"
            inputType="fancy_select"
            fancy_select_options={yes_no_default_options}
            info_description="Whether the model can process images as input."
            bind:value={override_supports_vision}
          />

          <FormElement
            label="Reasoning Capable (Thinking Model)"
            id="reasoning_capable"
            inputType="fancy_select"
            fancy_select_options={reasoning_capable_options}
            info_description="Leave off if reasoning is optional. Only set to Yes if reasoning is always returned."
            bind:value={override_reasoning_capable}
          />

          <FormElement
            label="Output Parser"
            id="parser"
            inputType="fancy_select"
            fancy_select_options={parser_options}
            info_description="Special parsing for model output. Use R1 Thinking for models that return reasoning in <think> tags."
            bind:value={override_parser}
          />
        </div>
      </div>
    </div>
  </div>
</Dialog>

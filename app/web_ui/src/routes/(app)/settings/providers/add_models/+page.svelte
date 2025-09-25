<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { provider_name_from_id } from "$lib/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import Collapse from "$lib/ui/collapse.svelte"
  import { getContext } from "svelte"
  import type { Writable } from "svelte/store"

  let connected_providers: [string, string][] = []
  let loading_providers = true
  let error: KilnError | null = null
  let custom_model_providers: any[] = []
  let new_model_provider: string | null = null
  let new_model_name: string | null = null
  let new_model: any = {}
  let edit_model_index: number | null = null

  const default_provider_values = {
    supports_structured_output: true,
    supports_data_gen: true,
    suggested_for_data_gen: false,
    untested_model: false,
    provider_finetune_id: null,
    structured_output_mode: "default",
    parser: null,
    formatter: null,
    reasoning_capable: false,
    supports_logprobs: false,
    suggested_for_evals: false,
    supports_function_calling: true,
    uncensored: false,
    suggested_for_uncensored_data_gen: false,
    tuned_chat_strategy: null,
    r1_openrouter_options: false,
    require_openrouter_reasoning: false,
    logprobs_openrouter_options: false,
    openrouter_skip_required_parameters: false,
    thinking_level: null,
    ollama_model_aliases: null,
    anthropic_extended_thinking: false,
    gemini_reasoning_enabled: false,
    siliconflow_enable_thinking: null,
    reasoning_optional_for_structured_output: null,
  }

  let structured_output_mode = "default"
  let parser = ""
  let formatter = ""
  let tuned_chat_strategy = ""
  let thinking_level = ""
  let siliconflow_enable_thinking = "null"
  let reasoning_optional_for_structured_output = "null"
  let ollama_model_aliases_string = ""

  const bool_optional_options: [string, string][] = [
    ["null", "Default"],
    ["true", "True"],
    ["false", "False"],
  ]

  const structured_output_mode_options: [string, string][] = [
    ["default", "default"],
    ["json_schema", "json_schema"],
    ["function_calling_weak", "function_calling_weak"],
    ["function_calling", "function_calling"],
    ["json_mode", "json_mode"],
    ["json_instructions", "json_instructions"],
    ["json_instruction_and_object", "json_instruction_and_object"],
    ["json_custom_instructions", "json_custom_instructions"],
    ["unknown", "unknown"],
  ]

  const parser_options: [string, string][] = [
    ["", "(none)"],
    ["r1_thinking", "r1_thinking"],
    ["optional_r1_thinking", "optional_r1_thinking"],
  ]

  const formatter_options: [string, string][] = [
    ["", "(none)"],
    ["qwen3_style_no_think", "qwen3_style_no_think"],
  ]

  const chat_strategy_options: [string, string][] = [
    ["", "(none)"],
    ["final_only", "final_only"],
    ["final_and_intermediate", "final_and_intermediate"],
    ["two_message_cot", "two_message_cot"],
    [
      "final_and_intermediate_r1_compatible",
      "final_and_intermediate_r1_compatible",
    ],
  ]

  const thinking_level_options: [string, string][] = [
    ["", "(none)"],
    ["low", "low"],
    ["medium", "medium"],
    ["high", "high"],
  ]

  const load_existing_providers = async () => {
    try {
      loading_providers = true
      connected_providers = []
      let { data: settings, error: settings_error } =
        await client.GET("/api/settings")
      if (settings_error) {
        throw settings_error
      }
      if (!settings) {
        throw new KilnError("Settings not found", null)
      }
      custom_model_providers = settings["custom_model_providers"] || []
      if (
        (!custom_model_providers || custom_model_providers.length === 0) &&
        settings["custom_models"]
      ) {
        custom_model_providers = settings["custom_models"].map(
          (model_id: string) => {
            const [provider, model] = model_id.split("::", 2)
            return { name: provider, model_id: model, ...default_provider_values }
          },
        )
      }
      if (settings["open_ai_api_key"]) {
        connected_providers.push(["openai", "OpenAI"])
      }
      if (settings["groq_api_key"]) {
        connected_providers.push(["groq", "Groq"])
      }
      if (settings["bedrock_access_key"] && settings["bedrock_secret_key"]) {
        connected_providers.push(["amazon_bedrock", "AWS Bedrock"])
      }
      if (settings["open_router_api_key"]) {
        connected_providers.push(["openrouter", "OpenRouter"])
      }
      if (settings["fireworks_api_key"] && settings["fireworks_account_id"]) {
        connected_providers.push(["fireworks_ai", "Fireworks AI"])
      }
      if (settings["vertex_project_id"] && settings["vertex_location"]) {
        connected_providers.push(["vertex", "Vertex AI"])
      }
      if (settings["anthropic_api_key"]) {
        connected_providers.push(["anthropic", "Anthropic"])
      }
      if (settings["gemini_api_key"]) {
        connected_providers.push(["gemini_api", "Gemini"])
      }
      if (
        settings["azure_openai_api_key"] &&
        settings["azure_openai_endpoint"]
      ) {
        connected_providers.push(["azure_openai", "Azure OpenAI"])
      }
      if (settings["huggingface_api_key"]) {
        connected_providers.push(["huggingface", "Hugging Face"])
      }
      if (settings["together_api_key"]) {
        connected_providers.push(["together_ai", "Together AI"])
      }
      if (settings["siliconflow_cn_api_key"]) {
        connected_providers.push(["siliconflow_cn", "SiliconFlow (硅基流动)"])
      }
      if (connected_providers.length > 0) {
        new_model_provider = connected_providers[0][0] || null
      } else {
        new_model_provider = null
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading_providers = false
    }
  }

  onMount(async () => {
    await load_existing_providers()
  })

  function remove_model(model_index: number) {
    custom_model_providers = custom_model_providers.filter(
      (_, index) => index !== model_index,
    )
    save_model_list()
  }

  let add_model_dialog: Dialog | null = null

  function show_add_model_modal(index: number | null = null) {
    edit_model_index = index
    if (index !== null) {
      new_model = { ...default_provider_values, ...custom_model_providers[index] }
      new_model_provider = new_model.name
      new_model_name = new_model.model_id
      structured_output_mode = new_model.structured_output_mode || "default"
      parser = new_model.parser || ""
      formatter = new_model.formatter || ""
      tuned_chat_strategy = new_model.tuned_chat_strategy || ""
      thinking_level = new_model.thinking_level || ""
      siliconflow_enable_thinking =
        new_model.siliconflow_enable_thinking === null ||
        new_model.siliconflow_enable_thinking === undefined
          ? "null"
          : new_model.siliconflow_enable_thinking
          ? "true"
          : "false"
      reasoning_optional_for_structured_output =
        new_model.reasoning_optional_for_structured_output === null ||
        new_model.reasoning_optional_for_structured_output === undefined
          ? "null"
          : new_model.reasoning_optional_for_structured_output
          ? "true"
          : "false"
      ollama_model_aliases_string = new_model.ollama_model_aliases
        ? new_model.ollama_model_aliases.join(",")
        : ""
    } else {
      new_model = { ...default_provider_values }
      new_model_provider = connected_providers[0]?.[0] || null
      new_model_name = null
      structured_output_mode = "default"
      parser = ""
      formatter = ""
      tuned_chat_strategy = ""
      thinking_level = ""
      siliconflow_enable_thinking = "null"
      reasoning_optional_for_structured_output = "null"
      ollama_model_aliases_string = ""
    }
    add_model_dialog?.show()
  }

  function parse_optional_bool(val: string): boolean | null {
    if (val === "true") return true
    if (val === "false") return false
    return null
  }

  async function add_model() {
    if (
      new_model_provider &&
      new_model_provider.length > 0 &&
      new_model_name &&
      new_model_name.length > 0
    ) {
      new_model.name = new_model_provider
      new_model.model_id = new_model_name
      new_model.structured_output_mode = structured_output_mode
      new_model.parser = parser || null
      new_model.formatter = formatter || null
      new_model.tuned_chat_strategy = tuned_chat_strategy || null
      new_model.thinking_level = thinking_level || null
      new_model.siliconflow_enable_thinking = parse_optional_bool(
        siliconflow_enable_thinking,
      )
      new_model.reasoning_optional_for_structured_output = parse_optional_bool(
        reasoning_optional_for_structured_output,
      )
      new_model.ollama_model_aliases = ollama_model_aliases_string
        ? ollama_model_aliases_string
            .split(",")
            .map((s) => s.trim())
            .filter((s) => s.length > 0)
        : null
      if (edit_model_index !== null) {
        custom_model_providers[edit_model_index] = new_model
        custom_model_providers = [...custom_model_providers]
      } else {
        custom_model_providers = [...custom_model_providers, new_model]
      }
      await save_model_list()
      new_model_name = null
    } else {
      throw new KilnError(
        "Invalid model provider or name. Please try again with all fields.",
        null,
      )
    }

    return true
  }

  let saving_model_list = false
  let save_model_list_error: KilnError | null = null
  async function save_model_list() {
    try {
      saving_model_list = true
      let { data: save_result, error: save_error } = await client.POST(
        "/api/settings",
        { body: { custom_model_providers: custom_model_providers } },
      )
      if (save_error) {
        throw save_error
      }
      if (!save_result) {
        throw new KilnError("No response from server", null)
      }
    } catch (e) {
      save_model_list_error = createKilnError(e)
      // Re-throw the error so the dialog can can show it
      throw save_model_list_error
    } finally {
      saving_model_list = false
    }
  }

  function get_model_name(model: any) {
    return model.model_id
  }

  function get_provider_name(model: any) {
    return provider_name_from_id(model.name)
  }

  const lastPageUrl = getContext<Writable<URL | undefined>>("lastPageUrl")
  function get_breadcrumbs() {
    const breadcrumbs = [{ label: "Settings", href: "/settings" }]

    if ($lastPageUrl && $lastPageUrl.pathname === "/settings/providers") {
      breadcrumbs.push({ label: "AI Providers", href: "/settings/providers" })
    }

    return breadcrumbs
  }
</script>

<AppPage
  title="Manage Custom Models"
  sub_subtitle="Add/remove additional models from your connected AI providers, on top of those already included with Kiln."
  breadcrumbs={get_breadcrumbs()}
  action_buttons={custom_model_providers && custom_model_providers.length > 0
    ? [
        {
          label: "Add Model",
          primary: true,
          handler: () => show_add_model_modal(null),
        },
      ]
    : []}
>
  {#if loading_providers}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="alert alert-error">
        <span>{error.message}</span>
      </div>
    </div>
  {:else if custom_model_providers.length > 0}
    <div class="flex flex-col gap-4">
      {#each custom_model_providers as model, index}
        <div class="flex flex-row gap-2 card bg-base-200 py-2 px-4">
          <div class="font-medium min-w-24">
            {get_provider_name(model)}
          </div>
          <div class="grow">
            {get_model_name(model)}
          </div>
          <button
            on:click={() => show_add_model_modal(index)}
            class="link text-sm text-gray-500"
            >Edit</button
          >
          <button
            on:click={() => remove_model(index)}
            class="link text-sm text-gray-500">Remove</button
          >
        </div>
      {/each}
    </div>
  {:else}
    <div class="flex flex-col gap-4 justify-center items-center min-h-[30vh]">
      <button
        class="btn btn-wide btn-primary mt-4"
        on:click={() => show_add_model_modal(null)}
      >
        Add Model
      </button>
    </div>
  {/if}
  {#if saving_model_list}
    <div class="flex flex-row gap-2 mt-4">
      <div class="loading loading-spinner"></div>
      Saving
    </div>
  {:else if save_model_list_error}
    <div class="mt-4 text-error font-medium">
      <span>Error saving model list: {save_model_list_error.message}</span>
    </div>
  {/if}
</AppPage>

<Dialog
  bind:this={add_model_dialog}
  title={edit_model_index !== null ? "Edit Model" : "Add Model"}
  action_buttons=[
    { label: "Cancel", isCancel: true },
    {
      label: edit_model_index !== null ? "Save Model" : "Add Model",
      asyncAction: add_model,
      disabled: !new_model_provider || !new_model_name,
      isPrimary: true,
    },
  ]
>
  <div class="text-sm">Add a model from an existing provider.</div>
  <div class="text-sm text-gray-500 mt-3">
    Provide the exact model ID used by the provider API. For example, OpenAI's
    "gpt-3.5-turbo" or Groq's "gemma2-9b-it".
  </div>
  <div class="flex flex-col gap-4 mt-8">
    <FormElement
      label="Model Provider"
      id="model_provider"
      inputType="select"
      select_options={connected_providers}
      bind:value={new_model_provider}
    />
    <FormElement
      label="Model Name"
      id="model_name"
      inputType="input"
      bind:value={new_model_name}
    />
    <Collapse title="Advanced">
      <FormElement
        label="Supports Structured Output"
        id="supports_structured_output"
        inputType="checkbox"
        bind:value={new_model.supports_structured_output}
      />
      <FormElement
        label="Supports Data Generation"
        id="supports_data_gen"
        inputType="checkbox"
        bind:value={new_model.supports_data_gen}
      />
      <FormElement
        label="Suggested for Data Generation"
        id="suggested_for_data_gen"
        inputType="checkbox"
        bind:value={new_model.suggested_for_data_gen}
      />
      <FormElement
        label="Untested Model"
        id="untested_model"
        inputType="checkbox"
        bind:value={new_model.untested_model}
      />
      <FormElement
        label="Provider Finetune ID"
        id="provider_finetune_id"
        inputType="input"
        bind:value={new_model.provider_finetune_id}
        optional={true}
      />
      <FormElement
        label="Structured Output Mode"
        id="structured_output_mode"
        inputType="select"
        select_options={structured_output_mode_options}
        bind:value={structured_output_mode}
      />
      <FormElement
        label="Parser"
        id="parser"
        inputType="select"
        select_options={parser_options}
        bind:value={parser}
      />
      <FormElement
        label="Formatter"
        id="formatter"
        inputType="select"
        select_options={formatter_options}
        bind:value={formatter}
      />
      <FormElement
        label="Reasoning Capable"
        id="reasoning_capable"
        inputType="checkbox"
        bind:value={new_model.reasoning_capable}
      />
      <FormElement
        label="Supports Logprobs"
        id="supports_logprobs"
        inputType="checkbox"
        bind:value={new_model.supports_logprobs}
      />
      <FormElement
        label="Suggested for Evals"
        id="suggested_for_evals"
        inputType="checkbox"
        bind:value={new_model.suggested_for_evals}
      />
      <FormElement
        label="Supports Function Calling"
        id="supports_function_calling"
        inputType="checkbox"
        bind:value={new_model.supports_function_calling}
      />
      <FormElement
        label="Uncensored"
        id="uncensored"
        inputType="checkbox"
        bind:value={new_model.uncensored}
      />
      <FormElement
        label="Suggested for Uncensored Data Gen"
        id="suggested_for_uncensored_data_gen"
        inputType="checkbox"
        bind:value={new_model.suggested_for_uncensored_data_gen}
      />
      <FormElement
        label="Tuned Chat Strategy"
        id="tuned_chat_strategy"
        inputType="select"
        select_options={chat_strategy_options}
        bind:value={tuned_chat_strategy}
      />
      <FormElement
        label="R1 OpenRouter Options"
        id="r1_openrouter_options"
        inputType="checkbox"
        bind:value={new_model.r1_openrouter_options}
      />
      <FormElement
        label="Require OpenRouter Reasoning"
        id="require_openrouter_reasoning"
        inputType="checkbox"
        bind:value={new_model.require_openrouter_reasoning}
      />
      <FormElement
        label="Logprobs OpenRouter Options"
        id="logprobs_openrouter_options"
        inputType="checkbox"
        bind:value={new_model.logprobs_openrouter_options}
      />
      <FormElement
        label="OpenRouter Skip Required Parameters"
        id="openrouter_skip_required_parameters"
        inputType="checkbox"
        bind:value={new_model.openrouter_skip_required_parameters}
      />
      <FormElement
        label="Thinking Level"
        id="thinking_level"
        inputType="select"
        select_options={thinking_level_options}
        bind:value={thinking_level}
      />
      <FormElement
        label="Ollama Model Aliases"
        id="ollama_model_aliases"
        inputType="input"
        bind:value={ollama_model_aliases_string}
        optional={true}
      />
      <FormElement
        label="Anthropic Extended Thinking"
        id="anthropic_extended_thinking"
        inputType="checkbox"
        bind:value={new_model.anthropic_extended_thinking}
      />
      <FormElement
        label="Gemini Reasoning Enabled"
        id="gemini_reasoning_enabled"
        inputType="checkbox"
        bind:value={new_model.gemini_reasoning_enabled}
      />
      <FormElement
        label="SiliconFlow Enable Thinking"
        id="siliconflow_enable_thinking"
        inputType="select"
        select_options={bool_optional_options}
        bind:value={siliconflow_enable_thinking}
      />
      <FormElement
        label="Reasoning Optional for Structured Output"
        id="reasoning_optional_for_structured_output"
        inputType="select"
        select_options={bool_optional_options}
        bind:value={reasoning_optional_for_structured_output}
      />
    </Collapse>
  </div>
</Dialog>

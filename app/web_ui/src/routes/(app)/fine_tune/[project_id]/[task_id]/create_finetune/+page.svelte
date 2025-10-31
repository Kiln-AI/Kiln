<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client, base_url } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import type { ChatStrategy } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import Completed from "$lib/ui/completed.svelte"
  import { fine_tune_target_model as model_provider } from "$lib/stores"
  import {
    available_tuning_models,
    available_models_error,
    available_models_loading,
    get_available_models,
  } from "$lib/stores/fine_tune_store"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"

  import type {
    FinetuneProvider,
    DatasetSplit,
    Finetune,
    FineTuneParameter,
  } from "$lib/types"
  import SelectFinetuneDataset from "./select_finetune_dataset.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import RunConfigComponent from "$lib/ui/run_config_component/run_config_component.svelte"

  let finetune_description = ""
  let finetune_name = ""
  const disabled_header = "disabled_header"
  let data_strategy: ChatStrategy = "final_only"
  let finetune_custom_system_prompt = ""
  let finetune_custom_thinking_instructions =
    "Think step by step, explaining your reasoning."

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let run_config_component: RunConfigComponent | null = null
  $: system_prompt_method =
    run_config_component?.get_prompt_method() || "simple_prompt_builder"

  $: provider_id = $model_provider?.includes("/")
    ? $model_provider?.split("/")[0]
    : null
  $: base_model_id = $model_provider?.includes("/")
    ? $model_provider?.split("/").slice(1).join("/")
    : null

  let available_model_select: [string, string][] = []

  let selected_dataset: DatasetSplit | null = null
  $: selecting_thinking_dataset =
    selected_dataset?.filter?.includes("thinking_model")
  $: selected_dataset_has_val = selected_dataset?.splits?.find(
    (s) => s.name === "val",
  )
  $: selected_dataset_training_set_name = selected_dataset?.split_contents[
    "train"
  ]
    ? "train"
    : selected_dataset?.split_contents["all"]
      ? "all"
      : null

  $: step_3_visible = $model_provider && $model_provider !== disabled_header
  $: step_4_visible =
    $model_provider && $model_provider !== disabled_header && !!selected_dataset
  $: is_download = !!$model_provider?.startsWith("download_")
  $: step_5_download_visible = step_4_visible && is_download
  $: submit_visible = !!(step_4_visible && !is_download)

  onMount(async () => {
    get_available_models()
  })

  $: build_available_model_select($available_tuning_models)

  function build_available_model_select(models: FinetuneProvider[] | null) {
    if (!models) {
      return
    }
    available_model_select = []
    available_model_select.push([
      disabled_header,
      "Select a model to fine-tune",
    ])
    for (const provider of models) {
      for (const model of provider.models) {
        available_model_select.push([
          (provider.enabled ? "" : "disabled_") + provider.id + "/" + model.id,
          provider.name +
            ": " +
            model.name +
            (provider.enabled ? "" : " --- Requires API Key in Settings"),
        ])
      }
      // Providers with zero models should still appear and be disabled. Logging in will typically load their models
      if (!provider.enabled && provider.models.length === 0) {
        available_model_select.push([
          "disabled_" + provider.id,
          provider.name + " --- Requires API Key in Settings",
        ])
      }
    }
    available_model_select.push([
      "download_jsonl_msg",
      "Download: OpenAI chat format (JSONL)",
    ])
    available_model_select.push([
      "download_jsonl_json_schema_msg",
      "Download: OpenAI chat format with JSON response (JSONL)",
    ])
    available_model_select.push([
      "download_jsonl_toolcall",
      "Download: OpenAI chat format with tool call response (JSONL)",
    ])
    available_model_select.push([
      "download_huggingface_chat_template",
      "Download: HuggingFace chat template (JSONL)",
    ])
    available_model_select.push([
      "download_huggingface_chat_template_toolcall",
      "Download: HuggingFace chat template with tool calls (JSONL)",
    ])
    available_model_select.push([
      "download_vertex_gemini",
      "Download: Google Vertex-AI Gemini format (JSONL)",
    ])

    // Check if the model provider is in the available model select
    // If not, reset to disabled header. The list can change over time.
    if (!available_model_select.find((m) => m[0] === $model_provider)) {
      $model_provider = disabled_header
    }
  }

  const download_model_select_options: Record<string, string> = {
    download_jsonl_msg: "openai_chat_jsonl",
    download_jsonl_json_schema_msg: "openai_chat_json_schema_jsonl",
    download_jsonl_toolcall: "openai_chat_toolcall_jsonl",
    download_huggingface_chat_template: "huggingface_chat_template_jsonl",
    download_huggingface_chat_template_toolcall:
      "huggingface_chat_template_toolcall_jsonl",
    download_vertex_gemini: "vertex_gemini",
  }

  $: get_hyperparameters(provider_id)

  let hyperparameters: FineTuneParameter[] | null = null
  let hyperparameters_error: KilnError | null = null
  let hyperparameters_loading = true
  let hyperparameter_values: Record<string, string> = {}
  async function get_hyperparameters(provider_id: string | null) {
    if (!provider_id || provider_id === disabled_header) {
      return
    }
    try {
      hyperparameters_loading = true
      hyperparameters = null
      hyperparameter_values = {}
      if (is_download) {
        // No hyperparameters for download options
        return
      }
      const { data: hyperparameters_response, error: get_error } =
        await client.GET("/api/finetune/hyperparameters/{provider_id}", {
          params: {
            path: {
              provider_id,
            },
          },
        })
      if (get_error) {
        throw get_error
      }
      if (!hyperparameters_response) {
        throw new Error("Invalid response from server")
      }
      hyperparameters = hyperparameters_response
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        hyperparameters_error = new KilnError(
          "Could not load hyperparameters for fine-tuning.",
          null,
        )
      } else {
        hyperparameters_error = createKilnError(e)
      }
    } finally {
      hyperparameters_loading = false
    }
  }

  const type_strings: Record<FineTuneParameter["type"], string> = {
    int: "Integer",
    float: "Float",
    bool: "Boolean - 'true' or 'false'",
    string: "String",
  }

  function get_system_prompt_method_param(): string | undefined {
    return system_prompt_method === "custom" ? undefined : system_prompt_method
  }
  function get_custom_system_prompt_param(): string | undefined {
    return system_prompt_method === "custom"
      ? finetune_custom_system_prompt
      : undefined
  }
  function get_custom_thinking_instructions_param(): string | undefined {
    return system_prompt_method === "custom" &&
      data_strategy === "two_message_cot"
      ? finetune_custom_thinking_instructions
      : undefined
  }

  let create_finetune_error: KilnError | null = null
  let create_finetune_loading = false
  let created_finetune: Finetune | null = null
  async function create_finetune() {
    try {
      create_finetune_loading = true
      created_finetune = null
      if (!provider_id || !base_model_id) {
        throw new Error("Invalid model or provider")
      }

      // Filter out empty strings from hyperparameter_values, and parse/validate types
      const hyperparameter_values = build_parsed_hyperparameters()

      const { data: create_finetune_response, error: post_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/finetunes",
          {
            params: {
              path: {
                project_id,
                task_id,
              },
            },
            body: {
              dataset_id: selected_dataset?.id || "",
              provider: provider_id,
              base_model_id: base_model_id,
              train_split_name: selected_dataset_training_set_name || "",
              name: finetune_name ? finetune_name : undefined,
              description: finetune_description
                ? finetune_description
                : undefined,
              system_message_generator: get_system_prompt_method_param(),
              custom_system_message: get_custom_system_prompt_param(),
              custom_thinking_instructions:
                get_custom_thinking_instructions_param(),
              parameters: hyperparameter_values,
              data_strategy: data_strategy,
              validation_split_name: selected_dataset_has_val
                ? "val"
                : undefined,
            },
          },
        )
      if (post_error) {
        throw post_error
      }
      if (!create_finetune_response || !create_finetune_response.id) {
        throw new Error("Invalid response from server")
      }
      posthog.capture("create_finetune", {
        base_model: base_model_id,
        provider: provider_id,
        prompt_method: system_prompt_method,
      })
      created_finetune = create_finetune_response
      progress_ui_state.set({
        title: "Creating Fine-Tune",
        body: "In progress,  ",
        link: `/fine_tune/${project_id}/${task_id}/fine_tune/${created_finetune?.id}`,
        cta: "view job status",
        progress: null,
        step_count: 4,
        current_step: 3,
      })
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        create_finetune_error = new KilnError(
          "Could not create a dataset split for fine-tuning.",
          null,
        )
      } else {
        create_finetune_error = createKilnError(e)
      }
    } finally {
      create_finetune_loading = false
    }
  }

  function build_parsed_hyperparameters() {
    let parsed_hyperparameters: Record<string, string | number | boolean> = {}
    for (const hyperparameter of hyperparameters || []) {
      let raw_value = hyperparameter_values[hyperparameter.name]
      // remove empty strings
      if (!raw_value) {
        continue
      }
      let value = undefined
      if (hyperparameter.type === "int") {
        const parsed = parseInt(raw_value)
        if (
          isNaN(parsed) ||
          !Number.isInteger(parsed) ||
          parsed.toString() !== raw_value // checks it didn't parse 1.1 to 1
        ) {
          throw new Error(
            `Invalid integer value for ${hyperparameter.name}: ${raw_value}`,
          )
        }
        value = parsed
      } else if (hyperparameter.type === "float") {
        const parsed = parseFloat(raw_value)
        if (isNaN(parsed)) {
          throw new Error(
            `Invalid float value for ${hyperparameter.name}: ${raw_value}`,
          )
        }
        value = parsed
      } else if (hyperparameter.type === "bool") {
        if (raw_value !== "true" && raw_value !== "false") {
          throw new Error("Invalid boolean value: " + raw_value)
        }
        value = raw_value === "true"
      } else if (hyperparameter.type === "string") {
        value = raw_value
      } else {
        throw new Error("Invalid hyperparameter type: " + hyperparameter.type)
      }
      parsed_hyperparameters[hyperparameter.name] = value
    }
    return parsed_hyperparameters
  }

  async function download_dataset_jsonl(split_name: string) {
    const params = {
      dataset_id: selected_dataset?.id || "",
      project_id: project_id,
      task_id: task_id,
      split_name: split_name,
      data_strategy: data_strategy,
      format_type: $model_provider
        ? download_model_select_options[$model_provider]
        : undefined,
      system_message_generator: get_system_prompt_method_param(),
      custom_system_message: get_custom_system_prompt_param(),
      custom_thinking_instructions: get_custom_thinking_instructions_param(),
    }

    // Format params as query string, including escaping values and filtering undefined
    const query_string = Object.entries(params)
      .filter(([_, value]) => value !== undefined)
      .map(([key, value]) => `${key}=${encodeURIComponent(value || "")}`)
      .join("&")

    window.open(base_url + "/api/download_dataset_jsonl?" + query_string)
  }

  let data_strategy_select_options: [ChatStrategy, string][] = []

  function update_data_strategies_supported(
    model_provider: string | null,
    base_model_id: string | null,
    is_download: boolean,
    available_models: FinetuneProvider[] | null,
  ) {
    if (!model_provider || (!base_model_id && !is_download)) {
      return
    }

    const data_strategies_labels: Record<ChatStrategy, string> = {
      final_only: "Disabled - (Recommended)",
      two_message_cot: "Thinking - Learn both thinking and final response",
      final_and_intermediate:
        "Thinking - Learn both thinking and final response (Legacy Format)",
      final_and_intermediate_r1_compatible: is_download
        ? "Thinking (R1 compatible) - Learn both thinking and final response"
        : "Thinking - Learn both thinking and final response",
    }

    const r1_disabled_for_downloads = [
      // R1 data strategy currently disabled for toolcall downloads
      // because unclear how to use in the best way
      "download_huggingface_chat_template_toolcall",
      "download_jsonl_toolcall",

      // R1 currently not supported by Vertex models
      "download_vertex_gemini",
    ]
    if (r1_disabled_for_downloads.includes(model_provider)) {
      return ["final_only", "two_message_cot"]
    }

    const compatible_data_strategies: ChatStrategy[] = is_download
      ? [
          "final_only",
          "two_message_cot",
          "final_and_intermediate_r1_compatible",
        ]
      : available_models
          ?.map((model) => model.models)
          .flat()
          .find((model) => model.id === base_model_id)
          ?.data_strategies_supported ?? []

    data_strategy_select_options = compatible_data_strategies.map(
      (strategy) => [strategy, data_strategies_labels[strategy]],
    ) as [ChatStrategy, string][]

    data_strategy = compatible_data_strategies[0]
  }

  $: update_data_strategies_supported(
    $model_provider,
    base_model_id,
    is_download,
    $available_tuning_models,
  )

  function go_to_providers_settings() {
    progress_ui_state.set({
      title: "Creating Fine-Tune",
      body: "When you're done connecting providers, ",
      link: $page.url.pathname,
      cta: "return to fine-tuning",
      progress: null,
      step_count: 4,
      current_step: 1,
    })
    goto("/settings/providers?highlight=finetune")
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create a New Fine Tune"
    subtitle="Fine-tuned models learn from your dataset."
    breadcrumbs={[
      { label: "Fine Tunes", href: `/fine_tune/${project_id}/${task_id}` },
    ]}
  >
    {#if $available_models_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if created_finetune}
      <Completed
        title="Fine Tune Created"
        subtitle="It will take a while to complete training."
        link={`/fine_tune/${project_id}/${task_id}/fine_tune/${created_finetune?.id}`}
        button_text="View Fine Tune Job"
      />
    {:else if $available_models_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          Error Loading Available Models and Datasets
        </div>
        <div class="text-error text-sm">
          {$available_models_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else}
      <FormContainer
        {submit_visible}
        submit_label="Start Fine-Tune Job"
        on:submit={create_finetune}
        bind:error={create_finetune_error}
        bind:submitting={create_finetune_loading}
      >
        <div class="text-xl font-bold">
          Step 1: Select Base Model to Fine-Tune
        </div>
        <div>
          <FormElement
            label="Model & Provider"
            description="Select which model to fine-tune. Alternatively, download a JSONL file to fine-tune using any infrastructure."
            info_description="Connect providers in settings for 1-click fine-tuning. Alternatively, download a JSONL file to fine-tune using any infrastructure, like Unsloth or Axolotl."
            inputType="select"
            id="provider"
            select_options={available_model_select}
            bind:value={$model_provider}
          />
          <button
            class="mt-2 underline decoration-gray-400"
            on:click={go_to_providers_settings}
          >
            <Warning
              warning_message="For 1-click fine-tuning connect OpenAI, Fireworks, Together, or Google Vertex."
              warning_icon="info"
              warning_color="success"
              tight={true}
            />
          </button>
        </div>
        <div>
          <div class="text-xl font-bold mb-4">
            Step 2: Configure Fine-Tuning Run Settings
          </div>
          <RunConfigComponent
            bind:this={run_config_component}
            {project_id}
            hide_create_kiln_task_tool_button={true}
            hide_model_selector={true}
          />
        </div>

        {#if step_3_visible}
          <div>
            <div class="text-xl font-bold">
              Step 3: Select Fine-Tuning Dataset
            </div>
            <div class="font-light">
              Select a dataset to use for this fine-tune.
              <InfoTooltip
                tooltip_text="A fine-tuning dataset is a subset of your dataset which is used to train and validate the fine-tuned model. This is typically a subset of your dataset, which is intentionally kept separate from your eval data."
                position="bottom"
                no_pad={true}
              />
            </div>
          </div>
          <SelectFinetuneDataset {project_id} {task_id} bind:selected_dataset />
        {/if}

        {#if step_4_visible}
          <div class="text-xl font-bold">Step 4: Options</div>
          {#if system_prompt_method === "custom"}
            <div class="p-4 border-l-4 border-gray-300">
              <FormElement
                label="Custom System Prompt"
                description="Enter a custom system prompt to use during fine-tuning."
                info_description="There are tradeoffs to consider when choosing a system prompt for fine-tuning. Read more: https://platform.openai.com/docs/guides/fine-tuning/#crafting-prompts"
                inputType="textarea"
                id="finetune_custom_system_prompt"
                bind:value={finetune_custom_system_prompt}
              />
              {#if data_strategy === "two_message_cot"}
                <div class="mt-4"></div>
                <FormElement
                  label="Custom Thinking Instructions"
                  description="Instructions for the model's 'thinking' stage, before returning the final response."
                  info_description="When training with intermediate results (reasoning, chain of thought, etc.), this prompt will be used to ask the model to 'think' before returning the final response."
                  inputType="textarea"
                  id="finetune_custom_thinking_instructions"
                  bind:value={finetune_custom_thinking_instructions}
                />
              {/if}
            </div>
          {/if}
          <div>
            <FormElement
              label="Reasoning"
              description="Should the model be trained on reasoning/thinking content?"
              info_description="If you select 'Thinking', the model training will include thinking such as reasoning or chain of thought. Use this if you want to call the tuned model with a chain-of-thought prompt for additional inference time compute."
              inputType="select"
              id="data_strategy"
              select_options={data_strategy_select_options}
              bind:value={data_strategy}
            />
            {#if data_strategy === "two_message_cot" && !selecting_thinking_dataset}
              <Warning
                warning_message="You are training a model for inference-time thinking, but are not using a dataset filtered to samples with reasoning or chain-of-thought training data. This is not recommended, as it may lead to poor performance. We suggest creating a new dataset with a thinking filter."
                large_icon={true}
              />
            {/if}
            {#if data_strategy === "final_and_intermediate_r1_compatible" && !selecting_thinking_dataset}
              <Warning
                warning_message="You are training a 'thinking' model, but did not explicitly select a dataset filtered to samples with reasoning or chain-of-thought training data. If any of your training samples are missing reasoning data, it will error. If your data contains reasoning, you can ignore this warning."
                large_icon={true}
              />
            {/if}
          </div>
          {#if !is_download}
            <div class="collapse collapse-arrow bg-base-200">
              <input type="checkbox" class="peer" />
              <div class="collapse-title font-medium">Advanced Options</div>
              <div class="collapse-content flex flex-col gap-4">
                <FormElement
                  label="Name"
                  description="A name to identify this fine-tune. Leave blank and we'll generate one for you."
                  optional={true}
                  inputType="input"
                  id="finetune_name"
                  bind:value={finetune_name}
                />
                <FormElement
                  label="Description"
                  description="An optional description of this fine-tune."
                  optional={true}
                  inputType="textarea"
                  id="finetune_description"
                  bind:value={finetune_description}
                />
                {#if hyperparameters_loading}
                  <div class="w-full flex justify-center items-center">
                    <div class="loading loading-spinner loading-lg"></div>
                  </div>
                {:else if hyperparameters_error || !hyperparameters}
                  <div class="text-error text-sm">
                    {hyperparameters_error?.getMessage() ||
                      "An unknown error occurred"}
                  </div>
                {:else if hyperparameters.length > 0}
                  {#each hyperparameters as hyperparameter}
                    <FormElement
                      label={hyperparameter.name +
                        " (" +
                        type_strings[hyperparameter.type] +
                        ")"}
                      description={hyperparameter.description}
                      info_description="If you aren't sure, leave blank for default/recommended value. Ensure your value is valid for the type (e.g. an integer can't have decimals)."
                      inputType="input"
                      optional={hyperparameter.optional}
                      id={hyperparameter.name}
                      bind:value={hyperparameter_values[hyperparameter.name]}
                    />
                  {/each}
                {/if}
              </div>
            </div>
          {/if}
        {/if}
      </FormContainer>
    {/if}
    {#if step_5_download_visible}
      <div>
        <div class="text-xl font-bold">Step 5: Download JSONL</div>
        <div class="text-sm">
          Download JSONL files to fine-tune using any infrastructure, such as
          <a
            href="https://github.com/unslothai/unsloth"
            class="link"
            target="_blank">Unsloth</a
          >
          or
          <a
            href="https://github.com/axolotl-ai-cloud/axolotl"
            class="link"
            target="_blank">Axolotl</a
          >.
        </div>
        <div class="flex flex-col gap-4 mt-6">
          {#each Object.keys(selected_dataset?.split_contents || {}) as split_name}
            <button
              class="btn {Object.keys(selected_dataset?.split_contents || {})
                .length > 1
                ? 'btn-secondary btn-outline'
                : 'btn-primary'} max-w-[400px]"
              on:click={() => download_dataset_jsonl(split_name)}
            >
              Download Split: {split_name} ({selected_dataset?.split_contents[
                split_name
              ]?.length} examples)
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </AppPage>
</div>

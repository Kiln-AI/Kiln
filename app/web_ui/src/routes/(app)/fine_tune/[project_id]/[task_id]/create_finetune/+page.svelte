<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client, base_url } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import type { FinetuneDataStrategy } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import Completed from "$lib/ui/completed.svelte"
  import PromptTypeSelector from "../../../../run/prompt_type_selector.svelte"
  import { fine_tune_target_model as model_provider } from "$lib/stores"
  import {
    available_tuning_models,
    available_models_error,
    available_models_loading,
    get_available_models,
  } from "$lib/stores/fine_tune_store"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import { goto } from "$app/navigation"
  import { _ } from "svelte-i18n"

  import type {
    FinetuneProvider,
    DatasetSplit,
    Finetune,
    FineTuneParameter,
  } from "$lib/types"
  import SelectFinetuneDataset from "./select_finetune_dataset.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  let finetune_description = ""
  let finetune_name = ""
  const disabled_header = "disabled_header"
  let data_strategy: FinetuneDataStrategy = "final_only"
  let finetune_custom_system_prompt = ""
  let finetune_custom_thinking_instructions =
    "Think step by step, explaining your reasoning."
  let system_prompt_method = "simple_prompt_builder"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

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

  $: step_2_visible = $model_provider && $model_provider !== disabled_header
  $: step_3_visible =
    $model_provider && $model_provider !== disabled_header && !!selected_dataset
  $: is_download = !!$model_provider?.startsWith("download_")
  $: step_4_download_visible = step_3_visible && is_download
  $: submit_visible = !!(step_3_visible && !is_download)

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
      $_("finetune.select_model_to_finetune"),
    ])
    for (const provider of models) {
      for (const model of provider.models) {
        available_model_select.push([
          (provider.enabled ? "" : "disabled_") + provider.id + "/" + model.id,
          provider.name +
            ": " +
            model.name +
            (provider.enabled ? "" : $_("finetune.requires_api_key")),
        ])
      }
      // Providers with zero models should still appear and be disabled. Logging in will typically load their models
      if (!provider.enabled && provider.models.length === 0) {
        available_model_select.push([
          "disabled_" + provider.id,
          provider.name + $_("finetune.requires_api_key"),
        ])
      }
    }
    available_model_select.push([
      "download_jsonl_msg",
      $_("finetune.download_formats.openai_chat_jsonl"),
    ])
    available_model_select.push([
      "download_jsonl_json_schema_msg",
      $_("finetune.download_formats.openai_chat_json_schema_jsonl"),
    ])
    available_model_select.push([
      "download_jsonl_toolcall",
      $_("finetune.download_formats.openai_chat_toolcall_jsonl"),
    ])
    available_model_select.push([
      "download_huggingface_chat_template",
      $_("finetune.download_formats.huggingface_chat_template_jsonl"),
    ])
    available_model_select.push([
      "download_huggingface_chat_template_toolcall",
      $_("finetune.download_formats.huggingface_chat_template_toolcall_jsonl"),
    ])
    available_model_select.push([
      "download_vertex_gemini",
      $_("finetune.download_formats.vertex_gemini"),
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
          $_("finetune.could_not_load_hyperparameters"),
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
    int: $_("finetune.type_integer"),
    float: $_("finetune.type_float"),
    bool: $_("finetune.type_boolean"),
    string: $_("finetune.type_string"),
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
      data_strategy === "final_and_intermediate"
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
        throw new Error($_("finetune.invalid_model_provider"))
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
        throw new Error($_("finetune.invalid_response_from_server"))
      }
      created_finetune = create_finetune_response
      progress_ui_state.set({
        title: $_("finetune.creating_finetune"),
        body: $_("progress.in_progress") + ",  ",
        link: `/fine_tune/${project_id}/${task_id}/fine_tune/${created_finetune?.id}`,
        cta: $_("finetune.view_finetune_job"),
        progress: null,
        step_count: 4,
        current_step: 3,
      })
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        create_finetune_error = new KilnError(
          $_("finetune.could_not_create_dataset_split"),
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
            $_("finetune.invalid_integer", {
              values: { name: hyperparameter.name, value: raw_value },
            }),
          )
        }
        value = parsed
      } else if (hyperparameter.type === "float") {
        const parsed = parseFloat(raw_value)
        if (isNaN(parsed)) {
          throw new Error(
            $_("finetune.invalid_float", {
              values: { name: hyperparameter.name, value: raw_value },
            }),
          )
        }
        value = parsed
      } else if (hyperparameter.type === "bool") {
        if (raw_value !== "true" && raw_value !== "false") {
          throw new Error(
            $_("finetune.invalid_boolean", {
              values: { value: raw_value },
            }),
          )
        }
        value = raw_value === "true"
      } else if (hyperparameter.type === "string") {
        value = raw_value
      } else {
        throw new Error(
          $_("finetune.invalid_hyperparameter_type", {
            values: { type: hyperparameter.type },
          }),
        )
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

  let data_strategy_select_options: [FinetuneDataStrategy, string][] = []

  function update_data_strategies_supported(
    model_provider: string | null,
    base_model_id: string | null,
    is_download: boolean,
    available_models: FinetuneProvider[] | null,
  ) {
    if (!model_provider || !base_model_id) {
      return
    }

    const data_strategies_labels: Record<FinetuneDataStrategy, string> = {
      final_only: $_("finetune.disabled_recommended"),
      final_and_intermediate: $_("finetune.thinking_learn_both"),
      final_and_intermediate_r1_compatible: is_download
        ? $_("finetune.thinking_r1_compatible")
        : $_("finetune.thinking_learn_both"),
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
      return ["final_only", "final_and_intermediate"]
    }

    const compatible_data_strategies: FinetuneDataStrategy[] = is_download
      ? [
          "final_only",
          "final_and_intermediate",
          "final_and_intermediate_r1_compatible",
        ]
      : available_models
          ?.map((model) => model.models)
          .flat()
          .find((model) => model.id === base_model_id)
          ?.data_strategies_supported ?? []

    data_strategy_select_options = compatible_data_strategies.map(
      (strategy) => [strategy, data_strategies_labels[strategy]],
    ) as [FinetuneDataStrategy, string][]

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
      title: $_("finetune.creating_finetune"),
      body: $_("finetune.when_done_adding"),
      link: $page.url.pathname,
      cta: $_("finetune.return_to_finetuning"),
      progress: null,
      step_count: 4,
      current_step: 1,
    })
    goto("/settings/providers?highlight=finetune")
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("finetune.create_new_finetune")}
    subtitle={$_("finetune.finetune_subtitle")}
  >
    {#if $available_models_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if created_finetune}
      <Completed
        title={$_("finetune.finetune_created_title")}
        subtitle={$_("finetune.finetune_created_subtitle")}
        link={`/fine_tune/${project_id}/${task_id}/fine_tune/${created_finetune?.id}`}
        button_text={$_("finetune.view_finetune_job")}
      />
    {:else if $available_models_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          {$_("finetune.error_loading_models")}
        </div>
        <div class="text-error text-sm">
          {$available_models_error?.getMessage() || $_("errors.unknown_error")}
        </div>
      </div>
    {:else}
      <FormContainer
        {submit_visible}
        submit_label={$_("finetune.start_finetune_job")}
        on:submit={create_finetune}
        bind:error={create_finetune_error}
        bind:submitting={create_finetune_loading}
      >
        <div class="text-xl font-bold">
          {$_("finetune.step1_title")}
        </div>
        <div>
          <FormElement
            label={$_("finetune.model_provider_label")}
            description={$_("finetune.model_provider_description")}
            info_description={$_("finetune.model_provider_info")}
            inputType="select"
            id="provider"
            select_options={available_model_select}
            bind:value={$model_provider}
          />
          <button
            class="mt-1 underline decoration-gray-400"
            on:click={go_to_providers_settings}
          >
            <Warning
              warning_message={$_("finetune.connect_providers_warning")}
              warning_icon="info"
              warning_color="success"
              tight={true}
            />
          </button>
        </div>
        {#if step_2_visible}
          <div>
            <div class="text-xl font-bold">
              {$_("finetune.step2_title")}
            </div>
            <div class="font-light">
              {$_("finetune.select_dataset_description")}
              <InfoTooltip
                tooltip_text={$_("finetune.dataset_info_tooltip")}
                position="bottom"
                no_pad={true}
              />
            </div>
          </div>
          <SelectFinetuneDataset {project_id} {task_id} bind:selected_dataset />
        {/if}

        {#if step_3_visible}
          <div class="text-xl font-bold">{$_("finetune.step3_title")}</div>
          <PromptTypeSelector
            bind:prompt_method={system_prompt_method}
            description={$_("finetune.system_prompt_description")}
            info_description={$_("finetune.system_prompt_info")}
            exclude_cot={true}
            custom_prompt_name={$_("finetune.custom_finetune_prompt")}
          />
          {#if system_prompt_method === "custom"}
            <div class="p-4 border-l-4 border-gray-300">
              <FormElement
                label={$_("finetune.custom_system_prompt_label")}
                description={$_("finetune.custom_system_prompt_description")}
                info_description={$_("finetune.system_prompt_info")}
                inputType="textarea"
                id="finetune_custom_system_prompt"
                bind:value={finetune_custom_system_prompt}
              />
              {#if data_strategy === "final_and_intermediate"}
                <div class="mt-4"></div>
                <FormElement
                  label={$_("finetune.custom_thinking_instructions_label")}
                  description={$_(
                    "finetune.custom_thinking_instructions_description",
                  )}
                  info_description={$_(
                    "finetune.custom_thinking_instructions_info",
                  )}
                  inputType="textarea"
                  id="finetune_custom_thinking_instructions"
                  bind:value={finetune_custom_thinking_instructions}
                />
              {/if}
            </div>
          {/if}
          <div>
            <FormElement
              label={$_("finetune.reasoning_label")}
              description={$_("finetune.reasoning_description")}
              info_description={$_("finetune.reasoning_info")}
              inputType="select"
              id="data_strategy"
              select_options={data_strategy_select_options}
              bind:value={data_strategy}
            />
            {#if data_strategy === "final_and_intermediate" && !selecting_thinking_dataset}
              <Warning
                warning_message={$_("finetune.thinking_dataset_warning")}
                large_icon={true}
              />
            {/if}
            {#if data_strategy === "final_and_intermediate_r1_compatible" && !selecting_thinking_dataset}
              <Warning
                warning_message={$_("finetune.thinking_r1_warning")}
                large_icon={true}
              />
            {/if}
          </div>
          {#if !is_download}
            <div class="collapse collapse-arrow bg-base-200">
              <input type="checkbox" class="peer" />
              <div class="collapse-title font-medium">
                {$_("finetune.advanced_options")}
              </div>
              <div class="collapse-content flex flex-col gap-4">
                <FormElement
                  label={$_("finetune.finetune_name_label")}
                  description={$_("finetune.finetune_name_description")}
                  optional={true}
                  inputType="input"
                  id="finetune_name"
                  bind:value={finetune_name}
                />
                <FormElement
                  label={$_("finetune.finetune_description_label")}
                  description={$_("finetune.finetune_description_description")}
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
                      $_("errors.unknown_error")}
                  </div>
                {:else if hyperparameters.length > 0}
                  {#each hyperparameters as hyperparameter}
                    <FormElement
                      label={hyperparameter.name +
                        " (" +
                        type_strings[hyperparameter.type] +
                        ")"}
                      description={hyperparameter.description}
                      info_description={$_("finetune.hyperparameter_info")}
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
    {#if step_4_download_visible}
      <div>
        <div class="text-xl font-bold">{$_("finetune.step4_title")}</div>
        <div class="text-sm">
          {@html $_("finetune.download_jsonl_description", {
            values: {
              unsloth:
                '<a href="https://github.com/unslothai/unsloth" class="link" target="_blank">Unsloth</a>',
              axolotl:
                '<a href="https://github.com/axolotl-ai-cloud/axolotl" class="link" target="_blank">Axolotl</a>',
            },
          })}
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
              {$_("finetune.download_split", {
                values: {
                  split: split_name,
                  count: selected_dataset?.split_contents[split_name]?.length,
                },
              })}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </AppPage>
</div>

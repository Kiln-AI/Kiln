<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { page } from "$app/stores"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { formatDate } from "$lib/utils/formatters"
  import type { FinetuneDataStrategy } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"

  import PromptTypeSelector from "../../../../run/prompt_type_selector.svelte"

  import type {
    FinetuneProvider,
    DatasetSplit,
    Finetune,
    FineTuneParameter,
  } from "$lib/types"

  let finetune_description = ""
  let finetune_name = ""
  const disabled_header = "disabled_header"
  let model_provider = disabled_header
  let dataset_id = disabled_header
  let new_dataset_split = disabled_header
  let new_dataset_filter = disabled_header
  let automatic_validation = disabled_header
  let data_strategy: FinetuneDataStrategy = "final_only"
  let finetune_custom_system_prompt = ""
  let finetune_custom_thinking_instructions =
    "Think step by step, explaining your reasoning."
  let system_prompt_method = "basic"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let available_models: FinetuneProvider[] | null = null
  let available_model_select: [string, string][] = []
  let available_models_error: KilnError | null = null
  let available_models_loading = true

  $: selected_dataset = datasets?.find((d) => d.id === dataset_id)
  $: selecting_thinking_dataset =
    selected_dataset?.filter === "thinking_model" ||
    selected_dataset?.filter === "thinking_model_high_rated"
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
  // Only openai supports automatic validation
  $: show_automatic_validation_option =
    selected_dataset &&
    selected_dataset_has_val &&
    model_provider_id === "openai"
  $: step_3_visible =
    model_provider !== disabled_header &&
    !!selected_dataset &&
    (!show_automatic_validation_option ||
      automatic_validation !== disabled_header)
  $: is_download = model_provider.startsWith("download_")
  $: step_4_download_visible = step_3_visible && is_download
  $: submit_visible = step_3_visible && !is_download

  onMount(async () => {
    get_available_models()
    get_datasets()
  })

  async function get_available_models() {
    try {
      available_models_loading = true
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: available_models_response, error: get_error } =
        await client.GET("/api/finetune_providers", {})
      if (get_error) {
        throw get_error
      }
      if (!available_models_response) {
        throw new Error("Invalid response from server")
      }
      available_models = available_models_response
      build_available_model_select(available_models)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        available_models_error = new KilnError(
          "Could not load available models for fine-tuning.",
          null,
        )
      } else {
        available_models_error = createKilnError(e)
      }
    } finally {
      available_models_loading = false
    }
  }

  function build_available_model_select(models: FinetuneProvider[]) {
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
      "download_vertex_gemini_1_5",
      "Download: Google Vertex-AI Gemini 1.5 format (JSONL)",
    ])
    available_model_select.push([
      "download_gemini_api",
      "Download: Gemini API format (JSON)",
    ])
  }

  const download_model_select_options: Record<string, string> = {
    download_jsonl_msg: "openai_chat_jsonl",
    download_jsonl_json_schema_msg: "openai_chat_json_schema_jsonl",
    download_jsonl_toolcall: "openai_chat_toolcall_jsonl",
    download_huggingface_chat_template: "huggingface_chat_template_jsonl",
    download_huggingface_chat_template_toolcall:
      "huggingface_chat_template_toolcall_jsonl",
    download_vertex_gemini_1_5: "vertex_gemini_1_5",
    download_gemini_api: "gemini_api",
  }

  let datasets: DatasetSplit[] | null = null
  let datasets_error: KilnError | null = null
  let datasets_loading = true
  let dataset_select: [string, string][] = []
  async function get_datasets() {
    try {
      datasets_loading = true
      datasets = null
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: datasets_response, error: get_error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/dataset_splits",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (get_error) {
        throw get_error
      }
      if (!datasets_response) {
        throw new Error("Invalid response from server")
      }
      datasets = datasets_response
      build_available_dataset_select(datasets)
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        datasets_error = new KilnError(
          "Could not load datasets for fine-tuning.",
          null,
        )
      } else {
        datasets_error = createKilnError(e)
      }
    } finally {
      datasets_loading = false
    }
  }
  function build_available_dataset_select(datasets: DatasetSplit[]) {
    dataset_select = []
    dataset_select.push([disabled_header, "Select a dataset to fine-tune with"])
    for (const dataset of datasets) {
      dataset_select.push([
        "" + dataset.id,
        `${dataset.name} — Created ${formatDate(dataset.created_at)}`,
      ])
    }
    dataset_select.push(["new", "New Dataset"])
  }

  $: model_provider_id = model_provider.split("/")[0]
  $: if (model_provider !== disabled_header) {
    get_hyperparameters(model_provider.split("/")[0])
  }

  let hyperparameters: FineTuneParameter[] | null = null
  let hyperparameters_error: KilnError | null = null
  let hyperparameters_loading = true
  let hyperparameter_values: Record<string, string> = {}
  async function get_hyperparameters(provider_id: string) {
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

  $: handle_dataset_select(dataset_id)

  function handle_dataset_select(dataset_id_new: string) {
    if (dataset_id_new === "new") {
      dataset_id = disabled_header
      const modal = document.getElementById("create_dataset_modal")
      if (modal) {
        // @ts-expect-error daisyui functions not typed
        modal.showModal()
      }
    }
  }

  let create_dataset_split_error: KilnError | null = null
  let create_dataset_split_loading = false
  async function create_dataset() {
    try {
      create_dataset_split_loading = true
      create_dataset_split_error = null
      const { data: create_dataset_split_response, error: post_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/dataset_splits",
          {
            params: {
              path: {
                project_id,
                task_id,
              },
            },
            body: {
              // @ts-expect-error types are validated by the server
              dataset_split_type: new_dataset_split,
              // @ts-expect-error types are validated by the server
              filter_type: new_dataset_filter,
            },
          },
        )
      if (post_error) {
        throw post_error
      }
      if (!create_dataset_split_response || !create_dataset_split_response.id) {
        throw new Error("Invalid response from server")
      }
      if (!datasets) {
        datasets = []
      }
      datasets.push(create_dataset_split_response)
      build_available_dataset_select(datasets)
      dataset_id = create_dataset_split_response.id
      const modal = document.getElementById("create_dataset_modal")
      if (modal) {
        // @ts-expect-error daisyui functions not typed
        modal.close()
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        create_dataset_split_error = new KilnError(
          "Could not create a dataset split for fine-tuning.",
          null,
        )
      } else {
        create_dataset_split_error = createKilnError(e)
      }
    } finally {
      create_dataset_split_loading = false
    }
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
              dataset_id: dataset_id,
              provider: model_provider.split("/")[0],
              base_model_id: model_provider.split("/").slice(1).join("/"),
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
              validation_split_name:
                automatic_validation === "yes" ? "val" : undefined,
            },
          },
        )
      if (post_error) {
        throw post_error
      }
      if (!create_finetune_response || !create_finetune_response.id) {
        throw new Error("Invalid response from server")
      }
      created_finetune = create_finetune_response
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
      dataset_id: dataset_id,
      project_id: project_id,
      task_id: task_id,
      split_name: split_name,
      data_strategy: data_strategy,
      format_type: download_model_select_options[model_provider],
      system_message_generator: get_system_prompt_method_param(),
      custom_system_message: get_custom_system_prompt_param(),
      custom_thinking_instructions: get_custom_thinking_instructions_param(),
    }

    // Format params as query string, including escaping values and filtering undefined
    const query_string = Object.entries(params)
      .filter(([_, value]) => value !== undefined)
      .map(([key, value]) => `${key}=${encodeURIComponent(value || "")}`)
      .join("&")

    window.open(
      "http://localhost:8757/api/download_dataset_jsonl?" + query_string,
    )
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create a New Fine Tune"
    subtitle="Fine-tuned models learn on your dataset."
  >
    {#if available_models_loading || datasets_loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if created_finetune}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
        <svg
          fill="currentColor"
          class="size-10 text-success mb-2"
          viewBox="0 0 56 56"
          xmlns="http://www.w3.org/2000/svg"
          ><path
            d="M 27.9999 51.9063 C 41.0546 51.9063 51.9063 41.0781 51.9063 28 C 51.9063 14.9453 41.0312 4.0937 27.9765 4.0937 C 14.8983 4.0937 4.0937 14.9453 4.0937 28 C 4.0937 41.0781 14.9218 51.9063 27.9999 51.9063 Z M 27.9999 47.9219 C 16.9374 47.9219 8.1014 39.0625 8.1014 28 C 8.1014 16.9609 16.9140 8.0781 27.9765 8.0781 C 39.0155 8.0781 47.8983 16.9609 47.9219 28 C 47.9454 39.0625 39.0390 47.9219 27.9999 47.9219 Z M 25.0468 39.7188 C 25.8202 39.7188 26.4530 39.3437 26.9452 38.6172 L 38.5234 20.4063 C 38.8046 19.9375 39.0858 19.3984 39.0858 18.8828 C 39.0858 17.8047 38.1483 17.1484 37.1640 17.1484 C 36.5312 17.1484 35.9452 17.5 35.5234 18.2031 L 24.9296 35.1484 L 19.4921 28.1172 C 18.9765 27.4141 18.4140 27.1563 17.7812 27.1563 C 16.7499 27.1563 15.9296 28 15.9296 29.0547 C 15.9296 29.5703 16.1405 30.0625 16.4687 30.5078 L 23.0312 38.6172 C 23.6640 39.3906 24.2733 39.7188 25.0468 39.7188 Z"
          /></svg
        >
        <div class="font-medium mb-2">Fine Tune Created</div>
        <div class="max-w-96 text-center font-light">
          It will take a while to complete training.
          <div class="mt-8">
            <a
              href={`/fine_tune/${project_id}/${task_id}/fine_tune/${created_finetune?.id}`}
              class="btn btn-primary btn-wide"
            >
              View Fine Tune Job
            </a>
          </div>
        </div>
      </div>
    {:else if available_models_error || datasets_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          Error Loading Available Models and Datasets
        </div>
        <div class="text-error text-sm">
          {available_models_error?.getMessage() ||
            datasets_error?.getMessage() ||
            "An unknown error occurred"}
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
        <div class="text-xl font-bold">Step 1: Select Model</div>
        <FormElement
          label="Model & Provider"
          description="Select which model to fine-tune, and which provider to use. Optionally, download a JSONL file to fine-tune using any infrastructure."
          info_description="Fine-tuning requires a lot of compute. Generally we suggest you use a hosted cloud option, but if you have enough compute and expertise you can fine-tune on your own using tools like Unsloth, Axolotl, and others."
          inputType="select"
          id="provider"
          select_options={available_model_select}
          bind:value={model_provider}
        />
        {#if model_provider !== disabled_header}
          <div class="text-xl font-bold">Step 2: Select a Dataset</div>
          <FormElement
            label="Dataset"
            description="Select a dataset to fine-tune with."
            info_description="These datasets are subsets of the current task's data. We freeze a copy when you create a fine-tune so that you can create multiple fine-tunes from the same dataset for consistent evaluation."
            inputType="select"
            id="dataset"
            select_options={dataset_select}
            bind:value={dataset_id}
          />
          {#if selected_dataset}
            <div class="text-sm">
              The selected dataset has {selected_dataset.splits?.length}
              {selected_dataset.splits?.length === 1 ? "split" : "splits"}:
              <ul class="list-disc list-inside pt-2">
                {#each Object.entries(selected_dataset.split_contents) as [split_name, split_contents]}
                  <li>
                    {split_name.charAt(0).toUpperCase() +
                      split_name.slice(1)}:{" "}
                    {split_contents.length} examples
                    <span class="text-xs text-gray-500 pl-2">
                      {#if is_download}
                        <!-- Nothing -->
                      {:else if split_name === "val" && automatic_validation === disabled_header && show_automatic_validation_option}
                        May be used for validation during fine-tuning
                      {:else if split_name === "val" && automatic_validation === "yes"}
                        Will be used for validation during fine-tuning
                      {:else if split_name === "val"}
                        Will not be used, reserved for later evaluation
                      {:else if split_name === "test"}
                        Will not be used, reserved for later evaluation
                      {:else if split_name === selected_dataset_training_set_name}
                        Will be used for training
                      {/if}
                    </span>
                  </li>
                {/each}
              </ul>
            </div>
            {#if selected_dataset_training_set_name && selected_dataset.split_contents[selected_dataset_training_set_name]?.length < 100}
              <div class="text-sm">
                <span class="badge badge-error mr-2"
                  >Warning: Small Dataset</span
                >
                Your selected dataset has less than 100 examples for training. We
                strongly recommend creating a larger dataset before fine-tuning.
                Try our
                <a href={`/generate/${project_id}/${task_id}`} class="link">
                  generation tool
                </a>
                to expand your dataset.
              </div>
            {/if}
          {/if}
          {#if show_automatic_validation_option}
            <FormElement
              label="Automatic Validation"
              description="The selected dataset has a validation set. Should we use this for validation during fine-tuning? Select 'Yes' if your task is completely deterministic (classification), and 'No' if the task is not deterministic (e.g. generation)."
              inputType="select"
              id="automatic_validation"
              select_options={[
                [disabled_header, "Select if your task is deterministic"],
                ["yes", "Yes - My task is deterministic (classification)"],
                ["no", "No - My task is not deterministic (generation)"],
              ]}
              bind:value={automatic_validation}
            />
          {/if}
        {/if}

        {#if step_3_visible}
          <div class="text-xl font-bold">Step 3: Options</div>
          <PromptTypeSelector
            bind:prompt_method={system_prompt_method}
            description="The system message to use for fine-tuning. Choose the prompt you want to use with your fine-tuned model."
            info_description="There are tradeoffs to consider when choosing a system prompt for fine-tuning. Read more: https://platform.openai.com/docs/guides/fine-tuning/#crafting-prompts"
            exclude_cot={true}
            custom_prompt_name="Custom Fine Tuning Prompt"
          />
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
              {#if data_strategy === "final_and_intermediate"}
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
              label="Training Strategy"
              description="Should the model be trained on the final response only, or also include intermediate thinking?"
              info_description="If you select 'Final Response and Intermediate Thinking', the model will also be trained on the intermediate thinking such as reasoning or chain of thought. Use this if you want to call the tuned model with a chain-of-thought prompt for additional inference time compute."
              inputType="select"
              id="data_strategy"
              select_options={[
                ["final_only", "Final Response Only"],
                [
                  "final_and_intermediate",
                  "Final Response and Intermediate Thinking",
                ],
              ]}
              bind:value={data_strategy}
            />
            {#if data_strategy === "final_and_intermediate" && !selecting_thinking_dataset}
              <Warning
                warning_message="You are training a model for inference-time thinking, but are not using a dataset filtered to samples with reasoning or chain-of-thought training data. This is not recommended, as it may lead to poor performance. We suggest creating a new dataset with a thinking filter."
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
    {#if step_4_download_visible}
      <div>
        <div class="text-xl font-bold">Step 4: Download JSONL</div>
        <div class="text-sm">
          Download JSONL files to fine-tune using any infrastructure, such as
          <a
            href="https://github.com/axolotl-ai-cloud/axolotl"
            class="link"
            target="_blank">Axolotl</a
          >
          or
          <a
            href="https://github.com/unslothai/unsloth"
            class="link"
            target="_blank">Unsloth</a
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

<dialog id="create_dataset_modal" class="modal">
  <div class="modal-box">
    <form method="dialog">
      <button
        class="btn btn-sm text-xl btn-circle btn-ghost absolute right-2 top-2 focus:outline-none"
        >✕</button
      >
    </form>
    <h3 class="text-lg font-bold mb-2">Create a New Dataset Split</h3>
    <div class="font-light text-sm mb-6">
      A dataset split is a collection of examples from the current task. We
      freeze a copy when you create a fine-tune so that you can create multiple
      fine-tunes from the exactly same dataset.
    </div>
    <div class="flex flex-row gap-6 justify-center flex-col">
      <FormContainer
        submit_label="Create Dataset"
        on:submit={create_dataset}
        bind:error={create_dataset_split_error}
        bind:submitting={create_dataset_split_loading}
      >
        <FormElement
          label="Dataset Filter"
          description="Select a filter for your dataset. Typically you want to filter out examples that are not rated 4+ stars."
          info_description="A 'High Rating' filter will include only examples that are rated 4+ stars. The 'All' filter will include all examples. Thinking filters will also check the sample has reasoning or chain-of-thought data for training thinking models."
          inputType="select"
          optional={false}
          id="dataset_filter"
          select_options={[
            [disabled_header, "Select a dataset filter"],
            ["high_rating", "High Rating (4+ stars)"],
            ["all", "All (no filter)"],
            [
              "thinking_model",
              "Thinking (items with reasoning/chain-of-thought)",
            ],
            [
              "thinking_model_high_rated",
              "Thinking + High Rated (4+ stars and thinking)",
            ],
          ]}
          bind:value={new_dataset_filter}
        />
        <FormElement
          label="Dataset Splits"
          description="Select a splitting strategy for your dataset."
          info_description="You can split your dataset into training and evaluation sets, or use the entire dataset for training. If in doubt, select 'Train/Test' and we will split 80/20."
          inputType="select"
          optional={false}
          id="dataset_split"
          select_options={[
            [disabled_header, "Select a split strategy"],
            ["train_test", "Train/Test -- 80/20"],
            ["train_test_val", "Train/Test/Val -- 60/20/20"],
            ["train_test_val_80", "Train/Test/Val -- 80/10/10"],
            ["all", "Entire Dataset -- 100"],
          ]}
          bind:value={new_dataset_split}
        />
      </FormContainer>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>

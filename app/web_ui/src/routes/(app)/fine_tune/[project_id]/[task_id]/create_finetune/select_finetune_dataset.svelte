<script lang="ts">
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type {
    DatasetSplit,
    FinetuneDatasetInfo,
    FinetuneDatasetTagInfo,
  } from "$lib/types"
  import OptionList from "$lib/ui/option_list.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { goto } from "$app/navigation"
  import Warning from "$lib/ui/warning.svelte"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import { page } from "$app/stores"
  import { sets_equal } from "$lib/utils/collections"
  import ExistingDatasetButton from "./existing_dataset_button.svelte"

  let finetune_dataset_info: FinetuneDatasetInfo | null = null
  let filtered_tags: FinetuneDatasetTagInfo[] = []
  let loading = true
  let error: KilnError | null = null
  let valid_datasets: DatasetSplit[] = []
  let invalid_datasets: DatasetSplit[] = []

  export let project_id: string
  export let task_id: string
  export let selected_dataset: DatasetSplit | null = null
  export let required_tools: string[] = []

  function is_dataset_valid(
    dataset: DatasetSplit,
    required_tool_set: Set<string>,
    info: FinetuneDatasetInfo,
  ): boolean {
    const tool_info = info.tool_info_by_name[dataset.name]
    if (!tool_info) return true

    const dataset_tool_set = new Set(tool_info.tools || [])
    return (
      !tool_info.has_tool_mismatch &&
      sets_equal(required_tool_set, dataset_tool_set)
    )
  }

  function has_associated_finetunes(
    dataset: DatasetSplit,
    info: FinetuneDatasetInfo,
  ): boolean {
    if (!dataset.id) return false

    return info.existing_finetunes.some(
      (finetune) => finetune.dataset_split_id === dataset.id,
    )
  }

  function compute_disabled_datasets(
    required_tools: string[],
    info: FinetuneDatasetInfo | null,
  ): { valid_datasets: DatasetSplit[]; invalid_datasets: DatasetSplit[] } {
    if (!info) {
      return { valid_datasets: [], invalid_datasets: [] }
    }

    const required_tool_set = new Set(required_tools)
    const valid_datasets: DatasetSplit[] = []
    const invalid_datasets: DatasetSplit[] = []

    for (const dataset of info.existing_datasets) {
      const has_finetunes = has_associated_finetunes(dataset, info)
      const tools_match =
        !required_tools?.length ||
        is_dataset_valid(dataset, required_tool_set, info)

      // dataset without finetune is never shown
      if (!has_finetunes) {
        continue
      }

      if (tools_match) {
        valid_datasets.push(dataset)
      } else {
        invalid_datasets.push(dataset)
      }
    }

    return { valid_datasets, invalid_datasets }
  }

  $: ({ valid_datasets, invalid_datasets } = compute_disabled_datasets(
    required_tools,
    finetune_dataset_info,
  ))

  let create_dataset_dialog: Dialog | null = null
  let existing_dataset_dialog: Dialog | null = null

  let filter_to_reasoning_data = false
  let filter_to_highly_rated_data = false

  onMount(async () => {
    load_finetune_dataset_info()
  })

  async function load_finetune_dataset_info() {
    try {
      loading = true
      error = null
      if (!project_id || !task_id) {
        throw new Error("Project or task ID not set.")
      }
      const { data: finetune_dataset_info_response, error: get_error } =
        await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/finetune_dataset_info",
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
      if (!finetune_dataset_info_response) {
        throw new Error("Invalid response from server")
      }
      finetune_dataset_info = finetune_dataset_info_response
      filtered_tags = finetune_dataset_info_response.finetune_tags
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        error = new KilnError("Could not load fine-tune dataset info.", null)
      } else {
        error = createKilnError(e)
      }
    } finally {
      loading = false
    }
  }

  async function load_filtered_tags() {
    try {
      if (!project_id || !task_id) {
        return
      }

      const { data: filtered_tags_response, error: get_error } =
        await client.GET(
          "/api/projects/{project_id}/tasks/{task_id}/finetune_dataset_tags",
          {
            params: {
              path: {
                project_id,
                task_id,
              },
              query: {
                tool_names: required_tools.length > 0 ? required_tools : null,
              },
            },
          },
        )
      if (get_error) {
        throw get_error
      }
      if (filtered_tags_response) {
        filtered_tags = filtered_tags_response
      }
    } catch (e) {
      console.error("Error loading filtered tags:", e)
    }
  }

  $: if (finetune_dataset_info && required_tools) {
    load_filtered_tags()
  }

  $: tag_select_options = [
    {
      label: "Dataset Tags",
      options:
        filtered_tags?.map((tag) => ({
          label: tag.tag,
          value: tag.tag,
          description: `The tag '${tag.tag}' has ${tag.count} samples${required_tools.length > 0 ? " matching the selected tools" : ""}.`,
        })) || [],
    },
  ]

  $: show_existing_dataset_option =
    finetune_dataset_info?.existing_finetunes.length
  $: show_new_dataset_option = !!finetune_dataset_info
  $: new_dataset_disabled = filtered_tags.length === 0
  $: existing_dataset_disabled = valid_datasets.length === 0
  $: top_options = [
    {
      id: "add",
      name: "Add Fine-Tuning Data",
      description:
        "Add data for fine-tuning using synthetic data generation, CSV upload, or by tagging existing data.",
    },
    ...(show_existing_dataset_option
      ? [
          {
            id: "existing_dataset",
            name: "Reuse Dataset from an Existing Fine-Tune",
            description:
              "When comparing multiple base models, it's best to use exactly the same fine-tuning dataset.",
            disabled: existing_dataset_disabled,
          },
        ]
      : []),
    ...(show_new_dataset_option
      ? [
          {
            id: "new_dataset",
            name: "Create a New Fine-Tuning Dataset",
            description:
              "Create a new fine-tuning dataset by selecting a subset of your data.",
            disabled: new_dataset_disabled,
          },
        ]
      : []),
  ]

  async function select_top_option(option: string) {
    if (option === "new_dataset") {
      if (filtered_tags.length === 1) {
        dataset_tag = filtered_tags[0].tag
      }
      create_dataset_dialog?.show()
    } else if (option === "add") {
      show_add_data()
    } else if (option === "existing_dataset") {
      existing_dataset_dialog?.show()
    }
  }

  function edit_dataset() {
    selected_dataset = null
  }

  let new_dataset_split = "train_val"
  let dataset_tag: string | null = null
  $: selected_dataset_tag_data = filtered_tags.find(
    (t) => t.tag === dataset_tag,
  )
  let create_dataset_split_error: KilnError | null = null
  let create_dataset_split_loading = false
  async function create_dataset() {
    try {
      if (!dataset_tag) {
        throw new Error("No dataset tag selected")
      }
      create_dataset_split_loading = true
      create_dataset_split_error = null

      let dataset_filter_id = "tag::" + dataset_tag
      if (filter_to_reasoning_data || filter_to_highly_rated_data) {
        dataset_filter_id = "multi_filter::tag::" + dataset_tag
        if (filter_to_reasoning_data) {
          dataset_filter_id += "&thinking_model"
        }
        if (filter_to_highly_rated_data) {
          dataset_filter_id += "&high_rating"
        }
      }

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
              filter_id: dataset_filter_id,
            },
          },
        )
      if (post_error) {
        throw post_error
      }
      if (!create_dataset_split_response || !create_dataset_split_response.id) {
        throw new Error("Invalid response from server")
      }
      selected_dataset = create_dataset_split_response
      create_dataset_dialog?.close()
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

  function show_add_data() {
    progress_ui_state.set({
      title: "Creating Fine-Tune",
      body: "When you're done adding data, ",
      link: $page.url.pathname,
      cta: "return to fine-tuning",
      progress: null,
      step_count: 4,
      current_step: 2,
    })
    let link = `/dataset/${project_id}/${task_id}/add_data?reason=fine_tune&template_id=fine_tuning&splits=fine_tune_data:1.0&finetune_link=${encodeURIComponent(
      `/fine_tune/${project_id}/${task_id}/create_finetune`,
    )}`
    goto(link)
  }

  function finetune_names_from_dataset(dataset: DatasetSplit) {
    if (!dataset.id || !finetune_dataset_info) {
      return []
    }

    return finetune_dataset_info.existing_finetunes
      .filter((finetune) => finetune.dataset_split_id === dataset.id)
      .map((finetune) => finetune.name)
  }

  let new_dataset_filter_count: number | undefined = undefined
  $: if (selected_dataset_tag_data) {
    if (filter_to_reasoning_data && filter_to_highly_rated_data) {
      new_dataset_filter_count =
        selected_dataset_tag_data.reasoning_and_high_quality_count
    } else if (filter_to_reasoning_data) {
      new_dataset_filter_count = selected_dataset_tag_data.reasoning_count
    } else if (filter_to_highly_rated_data) {
      new_dataset_filter_count = selected_dataset_tag_data.high_quality_count
    } else {
      new_dataset_filter_count = selected_dataset_tag_data.count
    }
  } else {
    new_dataset_filter_count = undefined
  }

  function status_message(count: number) {
    if (count === 0) {
      return "Zero samples match your filters. Your dataset must include at least 1 sample. Please try a different filter or add more data."
    } else if (count < 50) {
      return `The dataset will only have ${count} samples. We suggest at least 50 samples for fine-tuning.`
    } else {
      return `The dataset will have ${count} samples.`
    }
  }

  // If the selected dataset is disabled, clear it
  // This handels the case where a dataset is selected, user goes back to select more tools and the dataset is no longer valid
  $: {
    const selected_dataset_id = selected_dataset?.id

    if (
      selected_dataset_id &&
      invalid_datasets.some((dataset) => dataset.id === selected_dataset_id)
    ) {
      selected_dataset = null
    }
  }
</script>

{#if loading}
  <div class="w-full flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if error}
  <div class="text-error text-sm">
    {error.getMessage() || "An unknown error occurred"}
  </div>
{:else if finetune_dataset_info}
  <div>
    {#if selected_dataset}
      <div class="flex flex-row gap-x-2">
        <div
          class="text-sm input input-bordered flex place-items-center w-full"
        >
          <div>
            Dataset '{selected_dataset.name}' created
            {formatDate(selected_dataset.created_at)}
          </div>
        </div>
        <button class="btn btn-sm btn-md" on:click={edit_dataset}
          >Change Dataset</button
        >
      </div>

      <div class="collapse collapse-arrow bg-base-200 mt-4">
        <input type="checkbox" class="peer" />
        <div class="collapse-title font-medium flex items-center">
          Training Dataset Details
        </div>
        <div class="collapse-content flex flex-col gap-4">
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
                    {#if split_name === "val"}
                      May be used for validation during fine-tuning
                    {:else if split_name === "test"}
                      Will not be used, reserved for later evaluation
                    {:else if split_name === "train" || split_name === "all"}
                      Will be used for training
                    {/if}
                  </span>
                </li>
              {/each}
            </ul>
          </div>
        </div>
      </div>
    {:else}
      <OptionList options={top_options} select_option={select_top_option} />
      {#if new_dataset_disabled || (existing_dataset_disabled && show_existing_dataset_option)}
        <div class="mt-4 max-w-[500px]">
          <Warning
            warning_message="No existing Fine-Tune datasets or Dataset Filter Tag that match your selected tools. Tool-based fine-tuning requires all runs in a dataset to use the exact same tools as your current selection. Consider adding data or adjusting your tool selection."
            warning_icon="exclaim"
            warning_color="primary"
          />
        </div>
      {/if}
    {/if}
  </div>
{/if}

<Dialog title="New Fine-Tuning Dataset" bind:this={create_dataset_dialog}>
  <div class="font-light text-sm mb-6">
    <div class="font-light text-sm mb-6">
      Snapshot a subset of your dataset to be used for fine-tuning.
    </div>
    <div class="flex flex-row gap-6 justify-center flex-col">
      <FormContainer
        submit_label="Create Dataset"
        on:submit={create_dataset}
        bind:error={create_dataset_split_error}
        bind:submitting={create_dataset_split_loading}
        submit_visible={new_dataset_filter_count !== undefined &&
          new_dataset_filter_count > 0}
      >
        <div class="flex flex-col gap-4">
          <FormElement
            label="Dataset Filter Tag (Required)"
            description="Select a tag. Only samples with this tag will be used in fine-tuning."
            info_description="Available tags start with 'fine_tune'. You can create custom tags with this prefix to organize different fine-tuning datasets."
            inputType="fancy_select"
            optional={false}
            id="dataset_filter"
            fancy_select_options={tag_select_options || []}
            bind:value={dataset_tag}
          />

          <FormElement
            inputType="checkbox"
            label="Filter to Reasoning Samples"
            info_description="Only samples with a thinking data (reasoning or chain of thought) will be included in the training dataset. Required when training a reasoning model."
            id="use_reasoning_data"
            bind:value={filter_to_reasoning_data}
          />
          <FormElement
            inputType="checkbox"
            label="Filter to Highly Rated Samples"
            info_description="Only samples with an overall rating of 4 or 5 stars will be included in the training dataset. Required when training a high-quality model."
            id="filter_to_highly_rated_data"
            bind:value={filter_to_highly_rated_data}
          />

          <div class="collapse collapse-arrow bg-base-200">
            <input type="checkbox" class="peer" />
            <div class="collapse-title font-medium flex items-center">
              Advanced Options
            </div>
            <div class="collapse-content flex flex-col gap-4">
              <FormElement
                label="Dataset Splits"
                description="Select ratios for splitting the data into training, validation, and test."
                info_description="If in doubt, leave the the recommended value. If you're using an external test set such as Kiln Evals, you don't need a test set here."
                inputType="select"
                optional={false}
                id="dataset_split"
                select_options={[
                  ["train_val", "80% Training, 20% Validation (Recommended)"],
                  ["train_test", "80% Training, 10% Test, 10% Validation"],
                  ["train_test_val", "60% Training, 20% Test, 20% Validation"],
                  [
                    "train_test_val_80",
                    "80% Training, 10% Test, 10% Validation",
                  ],
                  ["all", "100% Training"],
                ]}
                bind:value={new_dataset_split}
              />
            </div>
          </div>

          {#if new_dataset_filter_count !== undefined}
            <Warning
              warning_message={status_message(new_dataset_filter_count)}
              warning_icon={new_dataset_filter_count === 0 ? "exclaim" : "info"}
              warning_color={new_dataset_filter_count < 25
                ? "error"
                : new_dataset_filter_count < 50
                  ? "warning"
                  : "success"}
              large_icon={new_dataset_filter_count < 50}
            />
          {/if}
        </div>
      </FormContainer>
    </div>
  </div>
</Dialog>

<Dialog
  title="Select Dataset from an Existing Fine-Tune"
  bind:this={existing_dataset_dialog}
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
  ]}
>
  {#if !finetune_dataset_info}
    <div class="text-error">No existing fine-tune datasets found.</div>
  {:else}
    <div class="font-light text-sm mb-6">
      Select an existing fine-tuning dataset to use exactly the same data for
      this fine-tune.
    </div>
    <div class="flex flex-col gap-4 text-sm max-w-[600px]">
      {#each valid_datasets as dataset}
        {@const finetune_names = finetune_names_from_dataset(dataset)}
        <ExistingDatasetButton
          {dataset}
          finetuneNames={finetune_names}
          on:select={({ detail }) => {
            selected_dataset = detail
            existing_dataset_dialog?.close()
          }}
        />
      {/each}
    </div>
  {/if}
</Dialog>

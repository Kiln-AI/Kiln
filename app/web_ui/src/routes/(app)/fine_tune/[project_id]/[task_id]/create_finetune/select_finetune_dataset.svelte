<script lang="ts">
  import { onMount } from "svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import type { FinetuneDatasetInfo } from "$lib/types"
  import OptionList from "$lib/ui/option_list.svelte"
  import { formatDate } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { goto } from "$app/navigation"
  import type { DatasetSplit } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import { progress_ui_state } from "$lib/stores/progress_ui_store"
  import { page } from "$app/stores"
  import { _ } from "svelte-i18n"

  let finetune_dataset_info: FinetuneDatasetInfo | null = null
  let loading = true
  let error: KilnError | null = null

  export let project_id: string
  export let task_id: string
  export let selected_dataset: DatasetSplit | null = null

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

  $: tag_select_options = [
    {
      label: $_("finetune.dataset_filter_tag"),
      options:
        finetune_dataset_info?.finetune_tags?.map((tag) => ({
          label: tag.tag,
          value: tag.tag,
          description: `${$_("common.tags")} '${tag.tag}' ${$_("common.has")} ${tag.count} ${$_("common.samples")}.`,
        })) || [],
    },
  ]

  $: show_existing_dataset_option =
    finetune_dataset_info?.existing_finetunes.length
  $: show_new_dataset_option = finetune_dataset_info?.finetune_tags.length
  $: can_select_dataset =
    show_existing_dataset_option || show_new_dataset_option
  $: top_options = [
    ...(show_existing_dataset_option
      ? [
          {
            id: "existing_dataset",
            name: $_("finetune.reuse_existing_dataset"),
            description: $_("finetune.reuse_existing_description"),
          },
        ]
      : []),
    ...(show_new_dataset_option
      ? [
          {
            id: "new_dataset",
            name: $_("finetune.create_new_dataset"),
            description: $_("finetune.create_new_description"),
          },
        ]
      : []),
    ...(!can_select_dataset
      ? [
          {
            id: "add",
            name: $_("finetune.add_finetune_data"),
            description: $_("finetune.add_data_description"),
          },
        ]
      : []),
  ]

  function select_top_option(option: string) {
    if (option === "new_dataset") {
      if (finetune_dataset_info?.finetune_tags.length === 1) {
        dataset_tag = finetune_dataset_info?.finetune_tags[0].tag
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
  $: selected_dataset_tag_data = finetune_dataset_info?.finetune_tags.find(
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
      title: $_("finetune.creating_finetune"),
      body: $_("finetune.when_done_adding"),
      link: $page.url.pathname,
      cta: $_("finetune.return_to_finetuning"),
      progress: null,
      step_count: 4,
      current_step: 2,
    })
    let link = `/dataset/${project_id}/${task_id}/add_data?reason=fine_tune&splits=fine_tune_data:1.0&finetune_link=${encodeURIComponent(
      `/fine_tune/${project_id}/${task_id}/create_finetune`,
    )}`
    goto(link)
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
      return $_("finetune.zero_samples_error")
    } else if (count < 50) {
      return $_("finetune.few_samples_warning", { values: { count } })
    } else {
      return $_("finetune.samples_count_info", { values: { count } })
    }
  }
</script>

{#if loading}
  <div class="w-full flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if error}
  <div class="text-error text-sm">
    {error.getMessage() || $_("errors.unknown_error")}
  </div>
{:else if finetune_dataset_info}
  <div>
    {#if selected_dataset}
      <div class="flex flex-row gap-x-2">
        <div
          class="text-sm input input-bordered flex place-items-center w-full"
        >
          <div>
            {$_("finetune.dataset_created", {
              values: {
                name: selected_dataset.name,
                date: formatDate(selected_dataset.created_at),
              },
            })}
          </div>
        </div>
        <button class="btn btn-sm btn-md" on:click={edit_dataset}
          >{$_("finetune.change_dataset")}</button
        >
      </div>

      <div class="collapse collapse-arrow bg-base-200 mt-4">
        <input type="checkbox" class="peer" />
        <div class="collapse-title font-medium flex items-center">
          {$_("finetune.training_dataset_details")}
        </div>
        <div class="collapse-content flex flex-col gap-4">
          <div class="text-sm">
            {$_("finetune.dataset_has_splits", {
              values: { count: selected_dataset.splits?.length },
            })}
            <ul class="list-disc list-inside pt-2">
              {#each Object.entries(selected_dataset.split_contents) as [split_name, split_contents]}
                <li>
                  {split_name.charAt(0).toUpperCase() +
                    split_name.slice(1)}:{" "}
                  {$_("finetune.examples_count", {
                    values: { count: split_contents.length },
                  })}
                  <span class="text-xs text-gray-500 pl-2">
                    {#if split_name === "val"}
                      {$_("finetune.split_val")}
                    {:else if split_name === "test"}
                      {$_("finetune.split_test")}
                    {:else if split_name === "train" || split_name === "all"}
                      {$_("finetune.split_train")}
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
      {#if can_select_dataset}
        <div class="pt-4 font-light">
          {$_("common.or")}
          <button class="link font-normal" on:click={show_add_data}
            >{$_("finetune.add_additional_data")}</button
          >
          {$_("common.before_you_start")}.
        </div>
      {/if}
    {/if}
  </div>
{/if}

<Dialog
  title={$_("finetune.new_finetune_dataset")}
  bind:this={create_dataset_dialog}
>
  <div class="font-light text-sm mb-6">
    <div class="font-light text-sm mb-6">
      {$_("finetune.snapshot_subset")}
    </div>
    <div class="flex flex-row gap-6 justify-center flex-col">
      <FormContainer
        submit_label={$_("finetune.create_dataset")}
        on:submit={create_dataset}
        bind:error={create_dataset_split_error}
        bind:submitting={create_dataset_split_loading}
        submit_visible={new_dataset_filter_count !== undefined &&
          new_dataset_filter_count > 0}
      >
        <div class="flex flex-col gap-4">
          <FormElement
            label={$_("finetune.dataset_filter_tag")}
            description={$_("finetune.select_tag_description")}
            info_description={$_("finetune.available_tags_info")}
            inputType="fancy_select"
            optional={false}
            id="dataset_filter"
            fancy_select_options={tag_select_options || []}
            bind:value={dataset_tag}
          />

          <FormElement
            inputType="checkbox"
            label={$_("finetune.filter_reasoning_samples")}
            info_description={$_("finetune.reasoning_samples_info")}
            id="use_reasoning_data"
            bind:value={filter_to_reasoning_data}
          />
          <FormElement
            inputType="checkbox"
            label={$_("finetune.filter_highly_rated")}
            info_description={$_("finetune.highly_rated_info")}
            id="filter_to_highly_rated_data"
            bind:value={filter_to_highly_rated_data}
          />

          <div class="collapse collapse-arrow bg-base-200">
            <input type="checkbox" class="peer" />
            <div class="collapse-title font-medium flex items-center">
              {$_("finetune.advanced_options")}
            </div>
            <div class="collapse-content flex flex-col gap-4">
              <FormElement
                label={$_("finetune.dataset_splits")}
                description={$_("finetune.splits_description")}
                info_description={$_("finetune.splits_info")}
                inputType="select"
                optional={false}
                id="dataset_split"
                select_options={[
                  ["train_val", $_("finetune.train_val_80_20")],
                  ["train_test", $_("finetune.train_test_80_10_10")],
                  ["train_test_val", $_("finetune.train_test_val_60_20_20")],
                  ["train_test_val_80", $_("finetune.train_test_val_80_10_10")],
                  ["all", $_("finetune.all_training")],
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
  title={$_("finetune.select_existing_dataset")}
  bind:this={existing_dataset_dialog}
  action_buttons={[
    {
      label: $_("common.cancel"),
      isCancel: true,
    },
  ]}
>
  {#if !finetune_dataset_info}
    <div class="text-error">{$_("finetune.no_existing_datasets")}</div>
  {:else}
    <div class="font-light text-sm mb-6">
      {$_("finetune.select_existing_description")}
    </div>
    <div class="flex flex-col gap-4 text-sm max-w-[600px]">
      {#each finetune_dataset_info.existing_datasets as dataset}
        {@const finetunes = finetune_dataset_info.existing_finetunes.filter(
          (f) => f.dataset_split_id === dataset.id,
        )}
        {#if finetunes.length > 0 && dataset.id}
          <button
            class="card card-bordered border-base-300 bg-base-200 shadow-md w-full px-4 py-3 indicator grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 overflow-hidden text-left"
            on:click={() => {
              selected_dataset = dataset
              existing_dataset_dialog?.close()
            }}
          >
            <div class="text-xs text-gray-500">
              {$_("finetune.dataset_name")}
            </div>
            <div class="text-medium">{dataset.name}</div>
            <div class="text-xs text-gray-500">{$_("dataset.created_at")}</div>
            <div>{formatDate(dataset.created_at)}</div>

            <div class="text-xs text-gray-500">
              {$_("finetune.dataset_size")}
            </div>
            <div>
              {Object.keys(dataset.split_contents)
                .map((split_type) => {
                  return `${dataset.split_contents[split_type].length} ${$_("finetune.in_split", { values: { split: split_type } })}`
                })
                .join(", ")}
            </div>
            <div class="text-xs text-gray-500">
              {$_("finetune.tunes_using_dataset")}
            </div>
            <div>{finetunes.map((f) => f.name).join(", ")}</div>
          </button>
        {/if}
      {/each}
    </div>
  {/if}
</Dialog>

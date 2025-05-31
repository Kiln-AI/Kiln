<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadDatasetDialog from "../../../[project_id]/[task_id]/upload_dataset_dialog.svelte"
  import Completed from "$lib/ui/completed.svelte"
  import { goto } from "$app/navigation"
  import Splits from "$lib/ui/splits.svelte"
  import OptionList from "$lib/ui/option_list.svelte"
  import { _ } from "svelte-i18n"

  const validReasons = ["generic", "eval", "fine_tune"] as const
  type Reason = (typeof validReasons)[number]

  let manual_dialog: Dialog | null = null
  let upload_dataset_dialog: UploadDatasetDialog | null = null
  let splits: Record<string, number> = {}
  let splits_subtitle: string | undefined = undefined
  $: splitsArray = Object.entries(splits).map(([name, value]) => ({
    name,
    value,
  }))

  $: dataset_link = `/dataset/${$page.params.project_id}/${$page.params.task_id}`
  $: reason = validReasons.includes(
    $page.url.searchParams.get("reason") as Reason,
  )
    ? ($page.url.searchParams.get("reason") as Reason)
    : "generic"

  $: title =
    reason === "generic"
      ? $_("add_data.add_samples")
      : reason === "eval"
        ? $_("add_data.add_for_eval")
        : $_("add_data.add_for_finetune")
  $: reason_name =
    reason === "generic"
      ? $_("add_data.reason_names.dataset")
      : reason === "eval"
        ? $_("add_data.reason_names.eval")
        : $_("add_data.reason_names.fine_tune")

  $: data_source_descriptions = [
    {
      id: "synthetic",
      name: $_("add_data.synthetic_data"),
      description: $_("add_data.synthetic_data_description"),
      recommended: true,
    },
    {
      id: "csv",
      name: $_("add_data.upload_csv"),
      description: $_("add_data.upload_csv_description"),
    },
    ...(reason === "generic" && splitsArray.length === 0
      ? [
          {
            id: "run_task",
            name: $_("add_data.manually_run_task"),
            description: $_("add_data.manually_run_task_description", {
              values: { reason_name },
            }),
          },
        ]
      : []),
    ...(splitsArray.length > 0
      ? [
          {
            id: "manual",
            name: $_("add_data.manually_tag_existing_data"),
            description: $_("add_data.manually_tag_existing_data_description", {
              values: { reason_name },
            }),
          },
        ]
      : []),
  ]

  function select_data_source(id: string) {
    if (id === "manual") {
      manual_dialog?.show()
    } else if (id === "csv") {
      upload_dataset_dialog?.show()
    } else if (id === "run_task") {
      goto("/run")
    } else if (id === "synthetic") {
      goto(
        `/generate/${$page.params.project_id}/${$page.params.task_id}?reason=${reason}&splits=${$page.url.searchParams.get("splits")}`,
      )
    }
  }

  let completed = false
  let completed_link: string | null = null
  let completed_button_text: string | null = null

  function handleImportCompleted() {
    completed = true
    let eval_link = $page.url.searchParams.get("eval_link")
    let finetune_link = $page.url.searchParams.get("finetune_link")
    if (eval_link) {
      completed_link = eval_link
      completed_button_text = $_("add_data.return_to_eval")
    } else if (finetune_link) {
      completed_link = finetune_link
      completed_button_text = $_("add_data.return_to_finetune")
    }
  }
</script>

<AppPage {title} sub_subtitle={splits_subtitle}>
  <Splits bind:splits bind:subtitle={splits_subtitle} />
  {#if completed}
    <Completed
      title={$_("add_data.data_added")}
      subtitle={$_("add_data.data_added_subtitle")}
      link={completed_link || dataset_link}
      button_text={completed_button_text || $_("add_data.view_dataset")}
    />
  {:else}
    <OptionList
      options={data_source_descriptions}
      select_option={select_data_source}
    />
  {/if}
</AppPage>

<Dialog
  bind:this={manual_dialog}
  title={$_("add_data.manually_tag_dialog_title")}
  action_buttons={[
    {
      label: $_("common.cancel"),
      isCancel: true,
    },
    {
      label: $_("add_data.open_dataset"),
      isPrimary: true,
      action: () => {
        window.open(dataset_link, "_blank")
        return false
      },
    },
  ]}
>
  <div class="font-light flex flex-col gap-4">
    {#if splitsArray.length > 1}
      {@const tag_list = splitsArray
        .map((split) => `${Math.round(split.value * 100)}% ${split.name}`)
        .join(", ")}
      <div class="rounded-box bg-base-200 p-4 text-sm font-normal mt-4">
        {$_("add_data.adding_tags_proportions")}
        {tag_list}
      </div>
    {/if}
    <p>
      {$_("add_data.follow_steps_to_tag", { values: { reason_name } })}
    </p>

    <ol class="list-decimal list-inside flex flex-col gap-2 text-sm">
      <li class="ml-4">
        {@html $_("add_data.step_open_dataset", {
          values: {
            dataset_link: `<a href="${dataset_link}" class="link" target="_blank">${$_("add_data.dataset_page")}</a>`,
          },
        })}
      </li>
      <li class="ml-4">
        {$_("add_data.step_select_data")}
      </li>
      <li class="ml-4">
        {#if splitsArray.length > 1}
          {$_("add_data.step_click_tag_multiple")}
        {:else if splitsArray.length === 1}
          {$_("add_data.step_click_tag_single", {
            values: { tag_name: splitsArray[0].name },
          })}
        {/if}
      </li>
      {#if splitsArray.length > 1}
        <li class="ml-4">
          {$_("add_data.step_repeat_for_tags")}
        </li>
      {/if}
    </ol>
  </div>
</Dialog>

<UploadDatasetDialog
  bind:this={upload_dataset_dialog}
  onImportCompleted={handleImportCompleted}
  tag_splits={splits}
/>

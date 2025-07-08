<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadDatasetDialog from "../../../[project_id]/[task_id]/upload_dataset_dialog.svelte"
  import Completed from "$lib/ui/completed.svelte"
  import { goto } from "$app/navigation"
  import Splits from "$lib/ui/splits.svelte"
  import OptionList from "$lib/ui/option_list.svelte"

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
      ? "Add Samples to your Dataset"
      : reason === "eval"
        ? "Add Data for your Eval"
        : "Add Data for Fine-tuning"
  $: reason_name =
    reason === "generic" ? "dataset" : reason === "eval" ? "eval" : "fine tune"

  $: data_source_descriptions = [
    {
      id: "synthetic",
      name: "Synthetic Data",
      description: `Generate synthetic data using our interactive tool.`,
      recommended: true,
    },
    {
      id: "csv",
      name: "Upload CSV",
      description: `Add data by uploading a CSV file.`,
    },
    ...(reason === "generic" && splitsArray.length === 0
      ? [
          {
            id: "run_task",
            name: "Manually Run Task",
            description: `Each run will be saved to your ${reason_name}.`,
          },
        ]
      : []),
    ...(splitsArray.length > 0
      ? [
          {
            id: "manual",
            name: "Manually Tag Existing Data",
            description: `Tag existing data for use in your ${reason_name}.`,
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
      const params = new URLSearchParams()
      if (reason) params.set("reason", reason)
      const template_id = $page.url.searchParams.get("template_id")
      if (template_id) params.set("template_id", template_id)
      const eval_id = $page.url.searchParams.get("eval_id")
      if (eval_id) params.set("eval_id", eval_id)
      const splits_param = $page.url.searchParams.get("splits")
      if (splits_param) params.set("splits", splits_param)

      const query_string = params.toString()
      const url = `/generate/${$page.params.project_id}/${$page.params.task_id}?${query_string}`
      goto(url)
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
      completed_button_text = "Return to Eval"
    } else if (finetune_link) {
      completed_link = finetune_link
      completed_button_text = "Return to Fine-Tune"
    }
  }
</script>

<AppPage {title} sub_subtitle={splits_subtitle}>
  <Splits bind:splits bind:subtitle={splits_subtitle} />
  {#if completed}
    <Completed
      title="Data Added"
      subtitle="Your data has been added."
      link={completed_link || dataset_link}
      button_text={completed_button_text || "View Dataset"}
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
  title="Manually Tag Existing Data"
  action_buttons={[
    {
      label: "Cancel",
      isCancel: true,
    },
    {
      label: "Open Dataset",
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
        You will be adding tags in the following proportions:
        {tag_list}
      </div>
    {/if}
    <p>
      Follow these steps to manually tag existing data to be used for your {reason_name}.
    </p>

    <ol class="list-decimal list-inside flex flex-col gap-2 text-sm">
      <li class="ml-4">
        Open the <a href={dataset_link} class="link" target="_blank"
          >dataset page</a
        > in a new tab so you can follow these instructions.
      </li>
      <li class="ml-4">
        Using the "Select" button, select the data you to tag. You can select
        many examples at once using the shift key.
      </li>
      <li class="ml-4">
        Click the "Tag" button, select "Add Tag", then add
        {#if splitsArray.length > 1}
          the desired tag.
        {:else if splitsArray.length === 1}
          the tag "{splitsArray[0].name}".
        {/if}
      </li>
      {#if splitsArray.length > 1}
        <li class="ml-4">
          Repeat steps 2-3 for each tag. Be sure to tag in the proportions
          described above.
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

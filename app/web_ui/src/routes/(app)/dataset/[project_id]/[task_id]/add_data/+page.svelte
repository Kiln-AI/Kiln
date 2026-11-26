<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import Dialog from "$lib/ui/dialog.svelte"
  import UploadDatasetDialog from "../../../[project_id]/[task_id]/upload_dataset_dialog.svelte"
  import Completed from "$lib/ui/completed.svelte"
  import { goto } from "$app/navigation"
  import OptionList from "$lib/ui/option_list.svelte"
  import {
    get_splits_from_url_param,
    get_splits_subtitle,
  } from "$lib/utils/splits_util"
  import { agentInfo } from "$lib/agent"
  import { load_task } from "$lib/stores"
  import type { Task } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import {
    eval_id_from_param,
    type EvalAddDataPlan,
  } from "$lib/utils/eval_add_data"
  import { load_eval_add_data_plan } from "./eval_add_data_flow"

  const validReasons = ["generic", "eval", "fine_tune"] as const
  type Reason = (typeof validReasons)[number]

  let manual_dialog: Dialog | null = null
  let upload_dataset_dialog: UploadDatasetDialog | null = null
  // The route's task, loaded so the CSV upload dialog documents the correct
  // (single- vs multi-turn) format for the task this page targets.
  let route_task: Task | null = null
  // What this flow carries forward to the data sources. An eval's comes from the eval
  // itself; the other reasons pass theirs in the URL.
  type AddDataContext = {
    template_id: string | null
    eval_id: string | null
    eval_link: string | null
    splits_param: string | null
    tool_id: string | null
  }

  let eval_plan: EvalAddDataPlan | null = null
  let eval_plan_loading = false
  let eval_plan_error: KilnError | null = null

  $: url_context = {
    template_id: $page.url.searchParams.get("template_id"),
    eval_id: $page.url.searchParams.get("eval_id"),
    eval_link: $page.url.searchParams.get("eval_link"),
    splits_param: $page.url.searchParams.get("splits"),
    tool_id: $page.url.searchParams.get("tool_id"),
  }
  $: context = (
    reason === "eval"
      ? eval_plan?.kind === "ready"
        ? {
            template_id: eval_plan.template_id,
            eval_id: eval_plan.full_eval_id,
            eval_link: eval_plan.eval_link,
            splits_param: eval_plan.splits_param,
            tool_id: eval_plan.tool_id,
          }
        : {
            template_id: null,
            eval_id: null,
            eval_link: null,
            splits_param: null,
            tool_id: null,
          }
      : url_context
  ) satisfies AddDataContext
  $: splits =
    reason === "eval" && eval_plan?.kind === "ready"
      ? eval_plan.splits
      : get_splits_from_url_param(context.splits_param)
  $: splits_subtitle = get_splits_subtitle(splits)
  $: splitsArray = Object.entries(splits).map(([name, value]) => ({
    name,
    value,
  }))

  $: agentInfo.set({
    name: "Add Data",
    description: `Add data to dataset for project ID ${$page.params.project_id}, task ID ${$page.params.task_id}. Options include manual entry, file upload, synthetic generation, and eval-based generation.`,
  })

  $: if ($page.params.project_id && $page.params.task_id) {
    load_route_task($page.params.project_id, $page.params.task_id)
  }

  async function load_route_task(req_project_id: string, req_task_id: string) {
    try {
      const loaded = await load_task(req_project_id, req_task_id)
      if (
        req_project_id !== $page.params.project_id ||
        req_task_id !== $page.params.task_id
      )
        return
      route_task = loaded
    } catch {
      // Fall back to single-turn CSV docs if the task can't be loaded; the
      // import still targets the route's task_id.
      route_task = null
    }
  }

  $: dataset_link = `/dataset/${$page.params.project_id}/${$page.params.task_id}`
  $: reason = validReasons.includes(
    $page.url.searchParams.get("reason") as Reason,
  )
    ? ($page.url.searchParams.get("reason") as Reason)
    : "generic"

  $: if (reason === "eval" && $page.params.project_id && $page.params.task_id) {
    load_plan(
      $page.params.project_id,
      $page.params.task_id,
      $page.url.searchParams.get("eval_id"),
    )
  }

  async function load_plan(
    req_project_id: string,
    req_task_id: string,
    eval_id_param: string | null,
  ) {
    const eval_id = eval_id_from_param(
      eval_id_param,
      req_project_id,
      req_task_id,
    )
    eval_plan = null
    eval_plan_error = null
    if (!eval_id) {
      eval_plan_error = createKilnError(
        new Error("This link names no eval of this task."),
      )
      return
    }
    eval_plan_loading = true
    try {
      const plan = await load_eval_add_data_plan(
        req_project_id,
        req_task_id,
        eval_id,
      )
      if (
        req_project_id !== $page.params.project_id ||
        req_task_id !== $page.params.task_id ||
        eval_id_param !== $page.url.searchParams.get("eval_id")
      )
        return
      eval_plan = plan
    } catch (e) {
      eval_plan_error = createKilnError(e)
    } finally {
      eval_plan_loading = false
    }
  }

  $: title =
    reason === "generic"
      ? "Add Samples to your Dataset"
      : reason === "eval"
        ? "Add Data for your Eval"
        : "Add Data for Fine-tuning"
  $: reason_name =
    reason === "generic" ? "dataset" : reason === "eval" ? "eval" : "fine tune"
  $: breadcrumbs =
    reason === "eval"
      ? [
          {
            label: "Evals",
            href: `/specs/${$page.params.project_id}/${$page.params.task_id}`,
          },
        ]
      : reason === "generic"
        ? [
            {
              label: "Dataset",
              href: `/dataset/${$page.params.project_id}/${$page.params.task_id}`,
            },
          ]
        : reason === "fine_tune"
          ? [
              {
                label: "Fine-tuning",
                href: `/fine_tune/${$page.params.project_id}/${$page.params.task_id}`,
              },
            ]
          : []

  $: data_source_descriptions = [
    {
      id: "synthetic",
      name: "Synthetic Data",
      description: `Generate synthetic data using our interactive tool.`,
      recommended: true,
    },
    {
      id: "csv",
      name: "Add CSV",
      description: `Add data from a CSV file.`,
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
      if (reason && reason !== "generic") params.set("reason", reason)
      if (context.template_id) params.set("template_id", context.template_id)
      if (context.eval_id) params.set("eval_id", context.eval_id)
      if (context.splits_param) params.set("splits", context.splits_param)

      // For reference answer evals, redirect to QnA page
      if (context.template_id === "rag") {
        if (context.eval_link) params.set("eval_link", context.eval_link)
        goto(
          `/generate/${$page.params.project_id}/${$page.params.task_id}/qna?${params.toString()}`,
        )
        return
      }

      if (context.tool_id) params.set("tool_id", context.tool_id)
      // Preserve an inherited empty fine-tuning tool/skill set when routing into SDG.
      // `fine_tuning_tools=` means "locked to no tools/skills", not "param missing".
      if ($page.url.searchParams.has("fine_tuning_tools")) {
        params.set(
          "fine_tuning_tools",
          $page.url.searchParams.get("fine_tuning_tools") ?? "",
        )
      }

      goto(
        `/generate/${$page.params.project_id}/${$page.params.task_id}?${params.toString()}`,
      )
    }
  }

  let completed = false
  let completed_link: string | null = null
  let completed_button_text: string | null = null

  function handleImportCompleted() {
    completed = true
    let eval_link = context.eval_link
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

<AppPage {title} sub_subtitle={splits_subtitle} {breadcrumbs}>
  {#if reason === "eval" && eval_plan_loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if reason === "eval" && eval_plan_error}
    <div class="max-w-[600px]">
      <Warning
        warning_color="error"
        warning_message={eval_plan_error.getMessage() ||
          "The eval could not be loaded."}
      />
    </div>
  {:else if reason === "eval" && eval_plan?.kind === "refused"}
    <div class="max-w-[600px] flex flex-col gap-4">
      <Warning warning_message={eval_plan.message} />
      <div>
        <a href={eval_plan.eval_link} class="btn">Return to Eval</a>
      </div>
    </div>
  {:else if completed}
    <Completed
      title="Data Added"
      subtitle="Your data has been added."
      link={completed_link || dataset_link}
      button_text={completed_button_text || "View Dataset"}
    />
  {:else}
    <div class="max-w-[600px]">
      <OptionList
        options={data_source_descriptions}
        select_option={select_data_source}
      />
    </div>
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
  turn_mode={route_task?.turn_mode ?? null}
/>

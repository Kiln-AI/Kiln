<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"
  import { client } from "$lib/api_client"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import type { Eval, FinetuneDatasetInfo } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"

  export let generate_subtopics: () => void
  export let generate_samples: () => void
  export let project_id: string
  export let task_id: string
  export let is_setup: boolean

  export let on_setup:
    | ((
        gen_type: "training" | "eval",
        template_id: string | null,
        eval_id: string | null,
        project_id: string,
        task_id: string,
        splits: Record<string, number>,
      ) => void)
    | undefined = undefined

  let evals_dialog: Dialog | null = null
  let evals_loading: boolean = false
  let evals: Eval[] = []
  let evals_error: KilnError | null = null
  async function get_evals() {
    try {
      evals_loading = true
      evals_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }
      evals = data
    } catch (error) {
      evals_error = createKilnError(error)
    } finally {
      evals_loading = false
    }
  }

  function show_evals_dialog() {
    evals_dialog?.show()
    get_evals()
  }

  function select_eval(evaluator: Eval) {
    const eval_set_filter_id = evaluator.eval_set_filter_id
    const eval_configs_filter_id = evaluator.eval_configs_filter_id
    const splits: Record<string, number> = {}
    if (
      eval_set_filter_id.startsWith("tag::") &&
      eval_configs_filter_id.startsWith("tag::")
    ) {
      const eval_set_tag = eval_set_filter_id.split("::")[1]
      const eval_configs_tag = eval_configs_filter_id.split("::")[1]
      splits[eval_set_tag] = 0.8
      splits[eval_configs_tag] = 0.2
    } else {
      alert(
        "We can't generate synthetic data for this eval as it's eval sets are not defined by tag filters. Select an eval which uses tags to define eval sets.",
      )
      return
    }
    const eval_id = project_id + "::" + task_id + "::" + (evaluator.id ?? "")
    const template_id = evaluator.template ?? null

    on_setup?.("eval", template_id, eval_id, project_id, task_id, splits)

    evals_dialog?.close()
  }

  let fine_tuning_dialog: Dialog | null = null
  let finetune_dataset_info_loading: boolean = false
  let finetune_dataset_info_error: KilnError | null = null
  let finetuning_tags: Record<string, number> = {}

  async function load_finetune_dataset_info() {
    try {
      finetune_dataset_info_loading = true
      finetune_dataset_info_error = null
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
      finetuning_tags = generate_fine_tuning_tags(
        finetune_dataset_info_response,
      )
      const keys = Object.keys(finetuning_tags)
      if (keys.length === 1 && keys[0] === "fine_tune_data") {
        // Special case: there is only one tag, and it's the fine_tune_data tag.
        // We don't need to show the dialog, just generate the data.
        generate_fine_tuning_data_for_tag("fine_tune_data")
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("Load failed")) {
        finetune_dataset_info_error = new KilnError(
          "Could not load fine-tune dataset info.",
          null,
        )
      } else {
        finetune_dataset_info_error = createKilnError(e)
      }
    } finally {
      finetune_dataset_info_loading = false
    }
  }

  function show_fine_tuning_dialog() {
    fine_tuning_dialog?.show()
    load_finetune_dataset_info()
  }

  function generate_fine_tuning_data_for_tag(tag: string) {
    const splits: Record<string, number> = {}
    splits[tag] = 1.0
    on_setup?.("training", "fine_tuning", null, project_id, task_id, splits)
    fine_tuning_dialog?.close()
  }

  function generate_fine_tuning_tags(dataset_info: FinetuneDatasetInfo | null) {
    // Always include the fine_tune_data tag, even if zero
    let tags: Record<string, number> = {
      fine_tune_data: 0,
    }
    for (const tag of dataset_info?.finetune_tags || []) {
      tags[tag.tag] = tag.count
    }
    tags = Object.fromEntries(Object.entries(tags).sort((a, b) => b[1] - a[1]))
    return tags
  }
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  {#if is_setup}
    <Intro
      title="Generate Data"
      description_paragraphs={[]}
      action_buttons={[
        {
          label: "Add Topics",
          onClick: () => generate_subtopics(),
          is_primary: true,
        },
        {
          label: "Generate Model Inputs",
          onClick: () => generate_samples(),
          is_primary: false,
        },
      ]}
    >
      <div slot="description">
        Adding topics will help generate diverse data. They can be nested,
        forming a topic tree. <a
          href="https://docs.kiln.tech/docs/synthetic-data-generation#topic-tree-data-generation"
          target="_blank"
          class="link">Guide</a
        >.
      </div>
      <div slot="icon">
        <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
        <svg
          class="w-10 h-10"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M22 10.5V12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2H13.5"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
          <path
            d="M16.652 3.45506L17.3009 2.80624C18.3759 1.73125 20.1188 1.73125 21.1938 2.80624C22.2687 3.88124 22.2687 5.62415 21.1938 6.69914L20.5449 7.34795M16.652 3.45506C16.652 3.45506 16.7331 4.83379 17.9497 6.05032C19.1662 7.26685 20.5449 7.34795 20.5449 7.34795M16.652 3.45506L10.6872 9.41993C10.2832 9.82394 10.0812 10.0259 9.90743 10.2487C9.70249 10.5114 9.52679 10.7957 9.38344 11.0965C9.26191 11.3515 9.17157 11.6225 8.99089 12.1646L8.41242 13.9M20.5449 7.34795L14.5801 13.3128C14.1761 13.7168 13.9741 13.9188 13.7513 14.0926C13.4886 14.2975 13.2043 14.4732 12.9035 14.6166C12.6485 14.7381 12.3775 14.8284 11.8354 15.0091L10.1 15.5876M10.1 15.5876L8.97709 15.9619C8.71035 16.0508 8.41626 15.9814 8.21744 15.7826C8.01862 15.5837 7.9492 15.2897 8.03811 15.0229L8.41242 13.9M10.1 15.5876L8.41242 13.9"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
      </div>
    </Intro>
  {:else}
    <div class="flex justify-center">
      <div
        class="grid grid-cols-2 gap-x-32 gap-y-4 items-start font-light text-sm"
        style="grid-template-columns: 270px 270px;"
      >
        <!-- Icons Row -->
        <div class="text-center">
          <div class="flex justify-center">
            <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
            <svg
              class="w-10 h-10"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2C16.714 2 19.0711 2 20.5355 3.46447C22 4.92893 22 7.28595 22 12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12Z"
                stroke="#1C274C"
                stroke-width="1.5"
              />
              <path
                d="M6 15.8L7.14286 17L10 14"
                stroke="#1C274C"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M6 8.8L7.14286 10L10 7"
                stroke="#1C274C"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M13 9L18 9"
                stroke="#1C274C"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M13 16L18 16"
                stroke="#1C274C"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </div>
        </div>
        <div class="text-center">
          <div class="flex justify-center">
            <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
            <svg
              class="w-10 h-10"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle
                cx="12"
                cy="12"
                r="2"
                transform="rotate(180 12 12)"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <circle
                cx="20"
                cy="14"
                r="2"
                transform="rotate(180 20 14)"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <circle
                cx="2"
                cy="2"
                r="2"
                transform="matrix(-1 8.74228e-08 8.74228e-08 1 6 8)"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <path
                d="M12 8L12 5"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M20 10L20 5"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M4 14L4 19"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M12 19L12 16"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M20 19L20 18"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M4 5L4 6"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </div>
        </div>

        <!-- Titles Row -->
        <div class="text-center">
          <h2 class="font-medium text-lg">Evals</h2>
        </div>
        <div class="text-center">
          <h2 class="font-medium text-lg">Fine-Tuning</h2>
        </div>

        <!-- Descriptions Row -->
        <div class="">
          <p class="">
            Generate data to evaluate model performance, including edge cases
            and challenging scenarios.
          </p>
        </div>
        <div class="">
          <p class="">
            Generate high-quality, diverse training examples for fine-tuning.
          </p>
        </div>

        <!-- Action Buttons Row -->
        <div class="">
          <button
            class="btn btn-primary w-full mt-4"
            on:click={show_evals_dialog}
          >
            Generate Eval Data
          </button>
        </div>
        <div class="">
          <button
            class="btn btn-primary w-full mt-4"
            on:click={show_fine_tuning_dialog}
          >
            Generate Fine-Tuning Data
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<Dialog title="Generate Synthetic Eval Data" bind:this={evals_dialog}>
  {#if evals_loading}
    <div class="flex justify-center my-16">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if evals_error}
    <div class="font-light">
      There was an error loading the evals. Please try again.
    </div>
    <div class="font-light text-error">
      {evals_error.message ?? "Unknown error"}
    </div>
  {:else if evals.length > 0}
    <div class="flex items-center mt-4">
      <a
        href={`/evals/${project_id}/${task_id}/create_evaluator`}
        class="btn btn-wide btn-outline mx-auto my-4"
      >
        Create a New Eval
      </a>
    </div>
    <div class="flex items-center mt-4">
      <div class="flex-1 border-t border-base-300"></div>
      <div class="px-4 text-sm font-light text-base-content/60">OR</div>
      <div class="flex-1 border-t border-base-300"></div>
    </div>
    <div class="font-medium text-center my-6">Select an Existing Eval</div>
    <div class="flex flex-col gap-3">
      {#each evals as evaluator}
        <button
          on:click={() => select_eval(evaluator)}
          class="card bg-base-100 border border-base-300 hover:border-primary hover:shadow-md transition-all duration-200 cursor-pointer"
        >
          <div class="p-4 text-sm text-left">
            <div class="">{evaluator.name}</div>
            {#if evaluator.description}
              <p class="text-xs text-gray-500 mt-1">
                {evaluator.description}
              </p>
            {/if}
          </div>
        </button>
      {/each}
    </div>
  {:else}
    <div class="font-light">
      <p class="mt-2 mb-6 text-sm">
        Create an evaluator to get started. This helps us understand what
        specific scenarios to generate data for.
      </p>
    </div>
    <div class="flex items-center mt-4">
      <a
        href={`/evals/${project_id}/${task_id}/create_evaluator`}
        class="btn btn-wide btn-primary mx-auto my-4"
      >
        Create a New Eval
      </a>
    </div>
  {/if}
</Dialog>

<Dialog
  title="Generate Synthetic Fine-Tuning Data"
  bind:this={fine_tuning_dialog}
>
  {#if finetune_dataset_info_loading}
    <div class="flex justify-center my-16">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if finetune_dataset_info_error}
    <div class="font-light">
      There was an error loading the fine-tune info. Please try again.
    </div>
    <div class="font-light text-error">
      {finetune_dataset_info_error.message ?? "Unknown error"}
    </div>
  {:else if Object.keys(finetuning_tags).length > 0}
    <!-- The single tag case is handled above -->
    <p class="font-light mt-2 mb-6 text-sm">
      Your project has multiple tags used for fine-tuning data. Select one to
      generate training data for:
    </p>
    {#each Object.keys(finetuning_tags) as tag}
      <div class="flex items-center mt-4">
        <button
          class="btn btn-wide mx-auto {tag === 'fine_tune_data'
            ? 'btn-primary'
            : ''}"
          on:click={() => generate_fine_tuning_data_for_tag(tag)}
        >
          Tag: {tag}
        </button>
      </div>
    {/each}
  {/if}
</Dialog>

<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import SelectEvalTemplate from "./select_eval_template.svelte"
  import type { EvalOutputScore, EvalTemplateId } from "$lib/types"
  import { type EvalTemplateResult } from "./eval_template"
  import FormContainer from "$lib/utils/form_container.svelte"
  import type { Task } from "$lib/types"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormList from "$lib/utils/form_list.svelte"
  import { load_task, load_rating_options } from "$lib/stores"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import Warning from "$lib/ui/warning.svelte"
  import { tick } from "svelte"
  import { client } from "$lib/api_client"
  import { goto } from "$app/navigation"
  import posthog from "posthog-js"

  // Loading
  let loading_task = true
  let loading_error: KilnError | undefined = undefined
  $: loading = loading_task
  let task: Task | null = null
  onMount(async () => {
    // Need to wait for the page params to be available
    await tick()
    try {
      task = await load_task($page.params.project_id, $page.params.task_id)
      eval_dataset_custom_tag = suggested_eval_set_tag
      config_dataset_custom_tag = suggested_config_set_tag
    } catch (e) {
      loading_error = createKilnError(e)
    } finally {
      loading_task = false
    }
  })

  let selected_template: EvalTemplateId | "none" | null = null
  let default_eval_tag: string | undefined = undefined
  let default_golden_tag: string | null = null
  let template_properties: Record<
    string,
    string | number | boolean | string[]
  > = {}
  let evaluation_data_type: string | undefined = undefined
  function on_selected_template(template: EvalTemplateResult) {
    // Populate out model from the template
    name = template.name
    description = template.description
    output_scores = template.output_scores
    selected_template = template.template_id
    default_eval_tag = template.default_eval_tag
    default_golden_tag = template.default_golden_tag
    template_properties = template.template_properties
    evaluation_data_type = template.evaluation_data_type
  }

  // Update default tag when a default tag is set
  $: if (default_eval_tag) {
    eval_dataset = "tag::" + default_eval_tag
  }
  $: if (default_golden_tag) {
    config_dataset = "tag::" + default_golden_tag
  }

  // Data for the creation
  let name: string = ""
  let description: string = ""
  let output_scores: EvalOutputScore[] = []
  let eval_dataset: string | undefined = undefined
  let eval_dataset_custom_tag: string = ""
  let config_dataset: string | undefined = undefined
  let config_dataset_custom_tag: string = ""

  // UI State
  let create_evaluator_error: KilnError | undefined = undefined
  let create_evaluator_loading: boolean = false
  // Used to not block the navigation once the evaluator is created
  let complete = false

  async function create_evaluator() {
    create_evaluator_error = undefined
    create_evaluator_loading = true
    try {
      if (!eval_dataset) {
        throw new Error("Please select both evaluation and config datasets")
      }
      let eval_configs_filter_id: string | null = null
      if (selected_template !== "rag") {
        if (!config_dataset) {
          throw new Error("Please select a config dataset")
        }
        eval_configs_filter_id =
          config_dataset === "custom_tag"
            ? "tag::" + config_dataset_custom_tag
            : config_dataset
      }
      let eval_set_filter_id =
        eval_dataset === "custom_tag"
          ? "tag::" + eval_dataset_custom_tag
          : eval_dataset

      const { data: create_evaluator_response, error: post_error } =
        await client.POST(
          "/api/projects/{project_id}/tasks/{task_id}/create_evaluator",
          {
            params: {
              path: {
                project_id: $page.params.project_id,
                task_id: $page.params.task_id,
              },
            },
            body: {
              name,
              description,
              output_scores,
              template: selected_template === "none" ? null : selected_template,
              eval_set_filter_id,
              eval_configs_filter_id,
              template_properties,
              evaluation_data_type: (evaluation_data_type || "final_answer") as
                | "final_answer"
                | "full_trace",
            },
          },
        )
      if (post_error) {
        throw post_error
      }
      posthog.capture("create_evaluator", {
        template: selected_template,
      })
      // Reload the rating options since the new eval may have added new options
      load_rating_options()
      // Redirect to add an eval config to this new eval
      complete = true
      goto(
        `/evals/${$page.params.project_id}/${$page.params.task_id}/${create_evaluator_response.id}`,
      )
    } catch (e) {
      create_evaluator_error = createKilnError(e)
    } finally {
      create_evaluator_loading = false
    }
  }

  $: suggested_eval_set_tag = default_eval_tag || "eval_set"
  $: suggested_config_set_tag = default_golden_tag || "golden"
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create New Evaluator"
    breadcrumbs={[
      {
        label: "Evals",
        href: `/evals/${$page.params.project_id}/${$page.params.task_id}`,
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Task Information</div>
        <div class="text-error text-sm">
          {loading_error?.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else if !selected_template}
      <SelectEvalTemplate
        selected_template_callback={on_selected_template}
        bind:task
      />
    {:else}
      <FormContainer
        submit_label="Create Evaluator"
        on:submit={create_evaluator}
        bind:error={create_evaluator_error}
        bind:submitting={create_evaluator_loading}
        warn_before_unload={!!(
          !complete &&
          (name ||
            description ||
            (output_scores.length > 0 && output_scores[0].name))
        )}
      >
        <div class="text-xl font-bold">Part 1: Evaluator Details</div>
        <FormElement
          label="Evaluator Name"
          description="A short name for your evaluator."
          inputType="input"
          id="name"
          bind:value={name}
        />
        <FormElement
          label="Evaluator Description"
          description="A short description of what this evaluator does."
          info_description="This is just for your reference. It will not be provided to the judge model during evals and is not a prompt."
          inputType="textarea"
          id="description"
          bind:value={description}
        />

        <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
          <div class="text-xl font-bold" id="requirements_part">
            Part 2: Evaluator Output Scores
          </div>
          <div class="text-xs text-gray-500">
            Define the scores that the evaluator will output.
          </div>
          {#if selected_template !== "none"}
            <Warning
              warning_message="Since you selected a template, you can't edit these. Use the 'Custom' template to create your own scores."
              warning_color="warning"
              tight={true}
            />
          {/if}
        </div>

        <FormList
          bind:content={output_scores}
          content_label="Output Score"
          let:item_index
          frozen={selected_template !== "none"}
        >
          <div class="flex flex-col gap-3">
            <div class="flex flex-row gap-1">
              <div class="grow flex flex-col gap-1">
                <FormElement
                  label="Score Name"
                  id="score_name_{item_index}"
                  light_label={true}
                  bind:value={output_scores[item_index].name}
                  max_length={32}
                  disabled={selected_template !== "none"}
                />
              </div>
              <div class="flex flex-col gap-1">
                <FormElement
                  label="Rating Type"
                  inputType="select"
                  id="score_type_{item_index}"
                  light_label={true}
                  select_options={[
                    ["five_star", "5 Star"],
                    ["pass_fail", "Pass / Fail"],
                    ["pass_fail_critical", "Pass / Fail / Critical"],
                  ]}
                  bind:value={output_scores[item_index].type}
                  disabled={selected_template !== "none"}
                />
              </div>
            </div>
            <div class="grow flex flex-col gap-1">
              <FormElement
                label="Instructions"
                inputType="textarea"
                id="score_instructions_{item_index}"
                light_label={true}
                bind:value={output_scores[item_index].instruction}
                disabled={selected_template !== "none"}
              />
            </div>
          </div>
        </FormList>

        <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
          <div class="text-xl font-bold" id="requirements_part">
            Part 3: Evaluation Dataset
          </div>
          <div class="text-xs text-gray-500">
            Specify which which part of your dataset is used when running your
            eval. You can create this data later.
          </div>
        </div>
        <FormElement
          label="Evaluation Dataset"
          inputType="fancy_select"
          info_description="You can populate this dataset later by adding this tag to samples in your dataset."
          id="automatic_validation"
          fancy_select_options={[
            {
              options: [
                {
                  label:
                    "Filter dataset to the '" +
                    suggested_eval_set_tag +
                    "' tag",
                  value: "tag::" + suggested_eval_set_tag,
                  badge: "Recommended",
                  badge_color: "primary",
                },
                {
                  label: "Filter dataset by a custom tag",
                  value: "custom_tag",
                },
                {
                  label: "Use every dataset item in the evaluation",
                  value: "all",
                  badge: "Not Recommended",
                },
              ],
            },
          ]}
          bind:value={eval_dataset}
        />

        {#if eval_dataset === "custom_tag"}
          <FormElement
            label="Evaluation Dataset Filter Tag"
            description="Your dataset will be filtered to only include items with this tag."
            id="custom_tag_eval_set"
            bind:value={eval_dataset_custom_tag}
          />
        {/if}

        {#if selected_template !== "rag"}
          <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
            <div class="text-xl font-bold" id="requirements_part">
              Part 4: Golden Dataset
            </div>
            <div class="text-xs text-gray-500">
              Specify which which part of your dataset is used when trying to
              find the best eval judge. You'll create and rate this data later.
            </div>
          </div>
          <FormElement
            label="Golden Dataset"
            info_description="You can populate this dataset later. We recommend you have a person rate all of the samples in this dataset, so you can find the judge which best matches human preferences."
            inputType="fancy_select"
            id="automatic_validation"
            fancy_select_options={[
              {
                options: [
                  {
                    label:
                      "Filter dataset to the '" +
                      suggested_config_set_tag +
                      "' tag",
                    value: "tag::" + suggested_config_set_tag,
                    badge: "Recommended",
                    badge_color: "primary",
                  },
                  {
                    label: "Filter dataset by a custom tag",
                    value: "custom_tag",
                  },
                  {
                    label: "Use every dataset item in the evaluation",
                    value: "all",
                    badge: "Not Recommended",
                  },
                ],
              },
            ]}
            bind:value={config_dataset}
          />

          {#if config_dataset === "custom_tag"}
            <FormElement
              label="Evaluation Config Dataset Filter Tag"
              description="Your dataset will be filtered to only include items with this tag."
              id="custom_tag_eval_set"
              bind:value={config_dataset_custom_tag}
            />
          {/if}
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>

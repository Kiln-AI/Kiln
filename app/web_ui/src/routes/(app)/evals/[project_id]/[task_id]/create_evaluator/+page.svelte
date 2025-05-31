<script lang="ts">
  import { _ } from "svelte-i18n"
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
  function on_selected_template(template: EvalTemplateResult) {
    // Populate out model from the template
    name = template.name
    description = template.description
    output_scores = template.output_scores
    selected_template = template.template_id
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
      if (!eval_dataset || !config_dataset) {
        throw new Error($_("evaluation.create_evaluator.select_datasets_error"))
      }
      // Validate the dataset filters
      let eval_configs_filter_id =
        config_dataset === "custom_tag"
          ? "tag::" + config_dataset_custom_tag
          : config_dataset
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
            },
          },
        )
      if (post_error) {
        throw post_error
      }
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

  // Default tags for each eval template
  const eval_set_default_tags: Record<EvalTemplateId | "none", string> = {
    kiln_requirements: "eval_set",
    toxicity: "toxicity_eval_set",
    bias: "bias_eval_set",
    maliciousness: "maliciousness_eval_set",
    factual_correctness: "factual_eval_set",
    jailbreak: "jailbreak_eval_set",
    none: "eval_set",
  }
  $: suggested_eval_set_tag =
    eval_set_default_tags[selected_template ?? "none"] || "eval_set"
  const config_set_default_tags: Record<EvalTemplateId | "none", string> = {
    kiln_requirements: "golden",
    toxicity: "toxicity_golden",
    bias: "bias_golden",
    maliciousness: "maliciousness_golden",
    factual_correctness: "factual_golden",
    jailbreak: "jailbreak_golden",
    none: "golden",
  }
  $: suggested_config_set_tag =
    config_set_default_tags[selected_template ?? "none"] || "golden"
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={$_("evaluation.create_evaluator.title")}
    subtitle={$_("evaluation.create_evaluator.subtitle")}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">
          {$_("evaluation.create_evaluator.error_loading_task")}
        </div>
        <div class="text-error text-sm">
          {loading_error?.getMessage() ||
            $_("evaluation.create_evaluator.unknown_error")}
        </div>
      </div>
    {:else if !selected_template}
      <SelectEvalTemplate
        selected_template_callback={on_selected_template}
        bind:task
      />
    {:else}
      <FormContainer
        submit_label={$_("evaluation.create_evaluator.create_evaluator")}
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
        <div class="text-xl font-bold">
          {$_("evaluation.create_evaluator.part1_title")}
        </div>
        <FormElement
          label={$_("evaluation.create_evaluator.evaluator_name")}
          description={$_(
            "evaluation.create_evaluator.evaluator_name_description",
          )}
          inputType="input"
          id="name"
          bind:value={name}
        />
        <FormElement
          label={$_("evaluation.create_evaluator.evaluator_description")}
          description={$_(
            "evaluation.create_evaluator.evaluator_description_description",
          )}
          inputType="textarea"
          id="description"
          bind:value={description}
        />

        <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
          <div class="text-xl font-bold" id="requirements_part">
            {$_("evaluation.create_evaluator.part2_title")}
          </div>
          <div class="text-xs text-gray-500">
            {$_("evaluation.create_evaluator.output_scores_description")}
          </div>
          {#if selected_template !== "none"}
            <Warning
              warning_message={$_(
                "evaluation.create_evaluator.template_warning",
              )}
              warning_color="warning"
              tight={true}
            />
          {/if}
        </div>

        <FormList
          bind:content={output_scores}
          content_label={$_("evaluation.create_evaluator.output_score")}
          let:item_index
          frozen={selected_template !== "none"}
        >
          <div class="flex flex-col gap-3">
            <div class="flex flex-row gap-1">
              <div class="grow flex flex-col gap-1">
                <FormElement
                  label={$_("evaluation.create_evaluator.score_name")}
                  id="score_name_{item_index}"
                  light_label={true}
                  bind:value={output_scores[item_index].name}
                  max_length={32}
                  disabled={selected_template !== "none"}
                />
              </div>
              <div class="flex flex-col gap-1">
                <FormElement
                  label={$_("evaluation.create_evaluator.rating_type")}
                  inputType="select"
                  id="score_type_{item_index}"
                  light_label={true}
                  select_options={[
                    ["five_star", $_("evaluation.create_evaluator.five_star")],
                    ["pass_fail", $_("evaluation.create_evaluator.pass_fail")],
                    [
                      "pass_fail_critical",
                      $_("evaluation.create_evaluator.pass_fail_critical"),
                    ],
                  ]}
                  bind:value={output_scores[item_index].type}
                  disabled={selected_template !== "none"}
                />
              </div>
            </div>
            <div class="grow flex flex-col gap-1">
              <FormElement
                label={$_("evaluation.create_evaluator.instructions")}
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
            {$_("evaluation.create_evaluator.part3_title")}
          </div>
          <div class="text-xs text-gray-500">
            {$_("evaluation.create_evaluator.evaluation_dataset_description")}
          </div>
        </div>
        <FormElement
          label={$_("evaluation.create_evaluator.evaluation_dataset")}
          inputType="select"
          info_description={$_(
            "evaluation.create_evaluator.evaluation_dataset_info",
          )}
          id="automatic_validation"
          select_options={[
            [
              "tag::" + suggested_eval_set_tag,
              $_("evaluation.create_evaluator.filter_recommended", {
                values: { tag: suggested_eval_set_tag },
              }),
            ],
            ["custom_tag", $_("evaluation.create_evaluator.filter_custom")],
            ["all", $_("evaluation.create_evaluator.use_all_data")],
          ]}
          bind:value={eval_dataset}
        />

        {#if eval_dataset === "custom_tag"}
          <FormElement
            label={$_("evaluation.create_evaluator.custom_tag_label")}
            description={$_(
              "evaluation.create_evaluator.custom_tag_description",
            )}
            id="custom_tag_eval_set"
            bind:value={eval_dataset_custom_tag}
          />
        {/if}

        <div class="text-sm font-medium text-left pt-6 flex flex-col gap-1">
          <div class="text-xl font-bold" id="requirements_part">
            {$_("evaluation.create_evaluator.part4_title")}
          </div>
          <div class="text-xs text-gray-500">
            {$_("evaluation.create_evaluator.eval_method_dataset_description")}
          </div>
        </div>
        <FormElement
          label={$_("evaluation.create_evaluator.eval_method_dataset")}
          info_description={$_(
            "evaluation.create_evaluator.eval_method_dataset_info",
          )}
          inputType="select"
          id="automatic_validation"
          select_options={[
            [
              "tag::" + suggested_config_set_tag,
              $_("evaluation.create_evaluator.filter_recommended", {
                values: { tag: suggested_config_set_tag },
              }),
            ],
            ["custom_tag", $_("evaluation.create_evaluator.filter_custom")],
            ["all", $_("evaluation.create_evaluator.use_all_data")],
          ]}
          bind:value={config_dataset}
        />

        {#if config_dataset === "custom_tag"}
          <FormElement
            label={$_("evaluation.create_evaluator.config_tag_label")}
            description={$_(
              "evaluation.create_evaluator.config_tag_description",
            )}
            id="custom_tag_eval_set"
            bind:value={config_dataset_custom_tag}
          />
        {/if}
      </FormContainer>
    {/if}
  </AppPage>
</div>

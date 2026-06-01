<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { create_eval_job } from "$lib/stores/job_creators"
  import {
    ui_state,
    model_info,
    load_model_info,
    load_task,
    get_task_composite_id,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import type { Eval, EvalConfig } from "$lib/types"
  import {
    can_submit_run_eval,
    eval_config_options,
    load_eval_judges,
    run_config_options,
    start_eval_job,
  } from "./run_eval_job"

  let dialog: Dialog | null = null

  $: project_id = $ui_state.current_project_id
  $: task_id = $ui_state.current_task_id
  $: has_task = !!project_id && !!task_id

  let evals: Eval[] | null = null
  let evals_loading = false
  let evals_error: KilnError | null = null
  // Bindable so tests can drive the eval-selection reactive path (FancySelect
  // can't be opened in jsdom).
  export let selected_eval_id: string | null = null

  let eval_configs: EvalConfig[] | null = null
  let eval_configs_loading = false
  let eval_configs_error: KilnError | null = null
  let default_eval_config_id: string | null = null
  let selected_eval_config_id: string | null = null

  let run_configs_loading = false
  let run_configs_error: KilnError | null = null
  let default_run_config_id: string | null = null
  let selected_run_config_id: string | null = null

  let submitting = false
  let submit_error: KilnError | null = null

  $: current_run_configs = task_id
    ? $run_configs_by_task_composite_id[
        get_task_composite_id(project_id ?? "", task_id)
      ] || null
    : null

  $: judge_select_options = eval_config_options(
    eval_configs,
    default_eval_config_id,
    $model_info,
  )
  $: run_config_select_options = run_config_options(
    current_run_configs,
    default_run_config_id,
    $model_info,
  )

  $: eval_select_options = evals
    ? [
        {
          label: "Evals",
          options: evals.map((e) => ({ value: e.id, label: e.name })),
        },
      ]
    : []

  $: submit_disabled =
    !has_task ||
    submitting ||
    !can_submit_run_eval({
      project_id,
      task_id,
      eval_id: selected_eval_id,
      eval_config_id: selected_eval_config_id,
      run_config_id: selected_run_config_id,
    })

  export function show() {
    submit_error = null
    dialog?.show()
    void on_open()
  }

  async function on_open() {
    // Reset selections each time the dialog opens.
    selected_eval_id = null
    eval_configs = null
    selected_eval_config_id = null
    default_eval_config_id = null
    default_run_config_id = null
    selected_run_config_id = null
    eval_configs_error = null
    run_configs_error = null
    if (!has_task) {
      return
    }
    void load_model_info()
    await Promise.all([load_evals(), load_run_configs()])
  }

  async function load_evals() {
    if (!project_id || !task_id) {
      return
    }
    evals = null
    evals_error = null
    evals_loading = true
    try {
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        { params: { path: { project_id, task_id } } },
      )
      if (error) {
        throw error
      }
      evals = data
    } catch (e) {
      evals_error = createKilnError(e)
    } finally {
      evals_loading = false
    }
  }

  async function load_run_configs() {
    if (!project_id || !task_id) {
      return
    }
    run_configs_error = null
    run_configs_loading = true
    try {
      await load_task_run_configs(project_id, task_id)
      const task = await load_task(project_id, task_id)
      default_run_config_id = task?.default_run_config_id ?? null
      if (!selected_run_config_id && default_run_config_id) {
        selected_run_config_id = default_run_config_id
      }
    } catch (e) {
      run_configs_error = createKilnError(e)
    } finally {
      run_configs_loading = false
    }
  }

  // When an eval is chosen, load it (for its default judge) and its judges.
  $: void on_eval_selected(selected_eval_id)
  async function on_eval_selected(eval_id: string | null) {
    eval_configs = null
    selected_eval_config_id = null
    default_eval_config_id = null
    eval_configs_error = null
    if (!eval_id || !project_id || !task_id) {
      return
    }
    eval_configs_loading = true
    try {
      // Bail out if the user switched evals while the GETs were in flight, so a
      // stale response can't clobber the newer eval's judge state.
      const result = await load_eval_judges(
        client.GET,
        { project_id, task_id, eval_id },
        () => selected_eval_id === eval_id,
      )
      if (result.stale) {
        return
      }
      eval_configs = result.eval_configs
      default_eval_config_id = result.default_eval_config_id
      selected_eval_config_id = result.selected_eval_config_id
    } catch (e) {
      if (selected_eval_id !== eval_id) {
        return
      }
      eval_configs_error = createKilnError(e)
    } finally {
      if (selected_eval_id === eval_id) {
        eval_configs_loading = false
      }
    }
  }

  async function submit() {
    submit_error = null
    submitting = true
    try {
      const started = await start_eval_job(create_eval_job, {
        project_id,
        task_id,
        eval_id: selected_eval_id,
        eval_config_id: selected_eval_config_id,
        run_config_id: selected_run_config_id,
      })
      if (started) {
        dialog?.close()
      }
    } catch (e) {
      submit_error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<Dialog bind:this={dialog} title="Run an Eval">
  {#if !has_task}
    <p class="text-sm text-gray-500">
      Select a task first to run an eval as a background job.
    </p>
  {:else}
    <div class="flex flex-col gap-4">
      <div>
        <FormElement
          id="run_eval_eval_select"
          label="Eval"
          description="Choose the eval to run."
          inputType="fancy_select"
          bind:value={selected_eval_id}
          fancy_select_options={eval_select_options}
          empty_label="Select an eval"
          empty_state_message="No evals for this task yet"
          disabled={evals_loading}
        />
        {#if evals_loading}
          <div class="text-xs text-gray-500 mt-1">Loading evals…</div>
        {:else if evals_error}
          <div class="text-error text-sm mt-1">
            {evals_error.getMessage() || "Could not load evals."}
          </div>
        {/if}
      </div>

      {#if selected_eval_id}
        <div>
          <FormElement
            id="run_eval_judge_select"
            label="Judge"
            description="Select the judge used to score outputs."
            inputType="fancy_select"
            bind:value={selected_eval_config_id}
            fancy_select_options={judge_select_options}
            empty_label="Select a judge"
            empty_state_message="No judges for this eval yet"
            disabled={eval_configs_loading}
          />
          {#if eval_configs_loading}
            <div class="text-xs text-gray-500 mt-1">Loading judges…</div>
          {:else if eval_configs_error}
            <div class="text-error text-sm mt-1">
              {eval_configs_error.getMessage() || "Could not load judges."}
            </div>
          {/if}
        </div>
      {/if}

      <div>
        <FormElement
          id="run_eval_run_config_select"
          label="Run Method"
          description="Select the run configuration to evaluate."
          inputType="fancy_select"
          bind:value={selected_run_config_id}
          fancy_select_options={run_config_select_options}
          empty_label="Select a run method"
          empty_state_message="No run methods for this task yet"
          disabled={run_configs_loading}
        />
        {#if run_configs_loading}
          <div class="text-xs text-gray-500 mt-1">Loading run methods…</div>
        {:else if run_configs_error}
          <div class="text-error text-sm mt-1">
            {run_configs_error.getMessage() || "Could not load run methods."}
          </div>
        {/if}
      </div>

      {#if submit_error}
        <div role="alert" class="alert alert-error text-sm">
          <span>{submit_error.getMessage() || "Could not start the eval."}</span
          >
        </div>
      {/if}

      <div class="flex flex-row justify-end mt-2">
        <button
          class="btn btn-sm h-10 min-w-24 btn-primary"
          disabled={submit_disabled}
          on:click={submit}
        >
          {#if submitting}
            <div class="loading loading-spinner loading-sm"></div>
          {/if}
          Run eval
        </button>
      </div>
    </div>
  {/if}
</Dialog>

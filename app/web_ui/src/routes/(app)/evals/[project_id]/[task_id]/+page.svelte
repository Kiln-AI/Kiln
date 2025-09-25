<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import EmptyEvaluator from "./empty_eval.svelte"
  import type { Eval } from "$lib/types"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import {
    model_info,
    load_model_info,
    model_name,
    prompt_name_from_id,
    current_task_prompts,
  } from "$lib/stores"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
    get_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import { prompt_link } from "$lib/utils/link_builder"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: current_task_run_configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] || null

  let evals: Eval[] | null = null
  let evals_error: KilnError | null = null
  let evals_loading = true

  $: is_empty = !evals || evals.length == 0
  $: sorted_evals = (
    evals
      ? [...evals].sort((a, b) => {
          // First sort by favorite status
          const favDiff = Number(b.favourite) - Number(a.favourite)
          if (favDiff !== 0) return favDiff
          // If favorite status is the same, sort by ID
          return (a.id || "").localeCompare(b.id || "")
        })
      : []
  ) as Eval[]

  onMount(async () => {
    // Wait for params to load
    await tick()
    // Usually cached and fast
    load_model_info()
    // Load the evals and run configs in parallel
    await Promise.all([get_evals(), get_task_run_configs()])
  })

  let run_configs_error: KilnError | null = null
  let run_configs_loading = true

  async function get_task_run_configs() {
    run_configs_loading = true
    try {
      await load_task_run_configs(project_id, task_id)
    } catch (err) {
      run_configs_error = createKilnError(err)
    } finally {
      run_configs_loading = false
    }
  }

  async function get_evals() {
    try {
      evals_loading = true
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

  let toggle_eval_favourite_error: KilnError | null = null

  $: loading = evals_loading || run_configs_loading
  $: error = evals_error || toggle_eval_favourite_error || run_configs_error

  async function toggle_eval_favourite(evaluator: Eval) {
    try {
      if (!evaluator.id) {
        throw new Error("Eval ID is required")
      }
      const new_fav_state = !evaluator.favourite
      const { data, error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/eval/{eval_id}/fav",
        {
          params: {
            path: { project_id, task_id, eval_id: evaluator.id },
          },
          body: { favourite: new_fav_state },
        },
      )
      if (error) {
        throw error
      }
      evaluator.favourite = data.favourite
      // Trigger reactivity
      evals = evals
    } catch (error) {
      toggle_eval_favourite_error = createKilnError(error)
    }
  }
</script>

<AppPage
  title="Evals"
  subtitle="Evaluate the quality of your prompts, models and tunes"
  sub_subtitle={is_empty ? undefined : "Read the Docs"}
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "New Evaluator",
          href: `/evals/${project_id}/${task_id}/create_evaluator`,
          primary: true,
        },
      ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if is_empty}
    <div class="flex flex-col items-center justify-center min-h-[60vh]">
      <EmptyEvaluator {project_id} {task_id} />
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if evals}
    <a href={`/evals/${project_id}/${task_id}/compare`} class="group">
      <div class="card border p-3 mb-4 rounded-md hover:bg-gray-50">
        <div class="flex flex-row gap-4 items-center">
          <div class="rounded-lg bg-blue-50 p-4">
            <svg
              class="h-12 aspect-760/621"
              viewBox="0 0 760 621"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <g clip-path="url(#clip0_1603_4)">
                <rect
                  x="10"
                  y="10"
                  width="740"
                  height="601"
                  rx="25"
                  fill="white"
                  stroke="#628BD9"
                  stroke-width="20"
                />
                <line
                  x1="137"
                  y1="90.9778"
                  x2="137.999"
                  y2="541.978"
                  stroke="#628BD9"
                  stroke-width="20"
                />
                <line
                  x1="656"
                  y1="490"
                  x2="82"
                  y2="490"
                  stroke="#628BD9"
                  stroke-width="20"
                />
                <circle cx="352" cy="241" r="28" fill="#628BD9" />
                <circle cx="473" cy="317" r="28" fill="#628BD9" />
                <circle cx="564" cy="153" r="28" fill="#628BD9" />
                <circle cx="232" cy="384" r="28" fill="#628BD9" />
              </g>
              <defs>
                <clipPath id="clip0_1603_4">
                  <rect width="760" height="621" fill="white" />
                </clipPath>
              </defs>
            </svg>
          </div>

          <div class="flex-grow flex flex-col text-sm justify-center">
            <span class="font-medium text-base"
              >Compare Models, Prompts and Fine-Tunes</span
            >
            <span class="text-sm font-light mt-1"
              >Find the best way to run this task by comparing models, prompts
              and fine-tunes using evals, cost and performance.</span
            >
            <button
              class="btn btn-xs btn-outline w-fit px-6 mt-2 group-hover:bg-secondary group-hover:text-secondary-content"
              >Compare Run Methods</button
            >
          </div>
        </div>
      </div>
    </a>

    <div class="text-xl font-bold mt-8 mb-2">All Evals</div>
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th></th>
            <th>Eval Name</th>
            <th>Description</th>
            <th>Selected Run Method</th>
          </tr>
        </thead>
        <tbody>
          {#each sorted_evals as evaluator}
            {@const run_config = current_task_run_configs?.find(
              (run_config) => run_config.id === evaluator.current_run_config_id,
            )}
            {@const prompt_href = run_config?.run_config_properties.prompt_id
              ? prompt_link(
                  project_id,
                  task_id,
                  run_config.run_config_properties.prompt_id,
                )
              : undefined}
            {@const prompt_name =
              run_config?.prompt?.name ||
              prompt_name_from_id(
                run_config?.run_config_properties.prompt_id || "",
                $current_task_prompts,
              )}
            <tr
              class="hover cursor-pointer"
              on:click={() => {
                goto(`/evals/${project_id}/${task_id}/${evaluator.id}`)
              }}
            >
              <td class="pr-0">
                <button
                  class="mask mask-star-2 h-5 w-5 pt-1 {evaluator.favourite
                    ? 'bg-amber-300 hover:bg-amber-400'
                    : 'bg-gray-300 hover:bg-gray-400'}"
                  on:click={(event) => {
                    event.stopPropagation()
                    toggle_eval_favourite(evaluator)
                  }}
                ></button>
              </td>
              <td> {evaluator.name} </td>
              <td> {evaluator.description} </td>
              <td>
                {#if run_config}
                  <div
                    class="grid grid-cols-[auto_1fr] gap-y-1 gap-x-4 lg:min-w-[260px]"
                  >
                    <div>Model:</div>
                    <div class="text-gray-500">
                      {model_name(
                        run_config.run_config_properties.model_name,
                        $model_info,
                      )}
                    </div>
                    <div>Prompt:</div>
                    <div class="text-gray-500">
                      {#if prompt_href}
                        <a href={prompt_href} class="link">{prompt_name}</a>
                      {:else}
                        {prompt_name}
                      {/if}
                    </div>
                  </div>
                {:else}
                  <div class="text-gray-500">N/A</div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</AppPage>

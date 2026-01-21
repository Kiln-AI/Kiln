<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import AppPage from "../../../../app_page.svelte"
  import { load_task } from "$lib/stores"
  import { checkDefaultRunConfigHasTools } from "../spec_utils"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let loading = true
  let default_run_config_has_tools = false
  let error: KilnError | null = null

  onMount(async () => {
    try {
      const task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Failed to load task")
      }
      default_run_config_has_tools = await checkDefaultRunConfigHasTools(
        project_id,
        task,
      )
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  function proceed_to_select_template() {
    goto(`/specs/${project_id}/${task_id}/select_template`)
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Create Spec"
    subtitle="Choose your Spec Creation Workflow"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
    breadcrumbs={[
      {
        label: "Specs & Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
    ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    {:else}
      <div class="my-4 max-w-[680px]">
        <div class="overflow-x-auto border-b">
          <table class="table table-fixed w-full">
            <colgroup>
              <col class="w-[240px]" />
              <col />
              <col />
            </colgroup>
            <thead>
              <tr class="border-b-0">
                <th></th>
                <th class="text-center text-lg">Manual</th>
                <th class="text-center text-lg">
                  <div class="flex items-center justify-center gap-2">
                    <img
                      src="/images/animated_logo.svg"
                      alt="Kiln Copilot"
                      class="size-4"
                    />
                    <span>Kiln Copilot</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th class="font-bold text-xs text-gray-500"
                  >Eval Judge Creation</th
                >
                <td class="text-center">Manual</td>
                <td class="text-center border-l">Automatic</td>
              </tr>
              <tr>
                <th class="font-bold text-xs text-gray-500"
                  >Edge Case Discovery</th
                >
                <td class="text-center">Manual</td>
                <td class="text-center border-l">Automatic</td>
              </tr>
              <tr>
                <th class="font-bold text-xs text-gray-500"
                  >Eval Data Creation</th
                >
                <td class="text-center">Manual</td>
                <td class="text-center border-l">Automatic</td>
              </tr>
              <tr>
                <th class="font-bold text-xs text-base-content/60"
                  >Eval Accuracy</th
                >
                <td class="text-center">Varies</td>
                <td class="text-center border-l">High</td>
              </tr>
              <tr>
                <th class="font-bold text-xs text-gray-500">Approx. Effort</th>
                <td class="text-center">20 min</td>
                <td class="text-center border-l">3 min</td>
              </tr>
              <tr>
                <th class="font-bold text-xs text-base-content/60"
                  >Kiln Account</th
                >
                <td class="text-center">Optional</td>
                <td class="text-center border-l">Required</td>
              </tr>
            </tbody>
          </table>
        </div>
        <table class="table-fixed w-full mt-4">
          <colgroup>
            <col class="w-[240px]" />
            <col />
            <col />
          </colgroup>
          <tbody>
            <tr>
              <td></td>
              <td class="text-center">
                <button
                  class="btn btn-outline btn-sm"
                  on:click={proceed_to_select_template}
                >
                  Create Manually
                </button>
              </td>
              <td class="text-center">
                <div
                  class="tooltip"
                  data-tip={default_run_config_has_tools
                    ? "Tool calling is not yet supported in Kiln Copilot. Please create the spec manually for now."
                    : undefined}
                >
                  <button
                    class="btn btn-primary btn-sm"
                    disabled={loading || default_run_config_has_tools}
                    on:click={() =>
                      goto(`/specs/copilot_auth`, {
                        replaceState: true,
                      })}
                  >
                    Connect Kiln Copilot
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    {/if}
  </AppPage>
</div>

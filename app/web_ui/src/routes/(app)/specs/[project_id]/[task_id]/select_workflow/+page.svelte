<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import AppPage from "../../../../app_page.svelte"
  import { load_task } from "$lib/stores"
  import {
    checkDefaultRunConfigHasTools,
    copilot_supported,
    spec_builder_url,
  } from "../spec_utils"
  import { checkKilnCopilotAvailable } from "$lib/utils/copilot_utils"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type { SpecType } from "$lib/types"
  import type { V2EvalType } from "$lib/utils/eval_types/registry"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: spec_type = $page.url.searchParams.get("type") as SpecType | null
  $: judge = $page.url.searchParams.get("judge") as V2EvalType | null
  $: agentInfo.set({
    name: "Select Eval Workflow",
    description: `Select an eval workflow as part of the eval creation process for project ID ${project_id}, task ID ${task_id}. Choose between guided and advanced eval creation.`,
  })

  let loading = true
  let connecting_pro = false
  let error: KilnError | null = null

  // This screen sits between the template/judge pickers and the spec builder,
  // and only renders when Kiln Pro could actually assist. Landing here without
  // a template (stale bookmark, or the pre-reorder entry URL) restarts the
  // flow; landing with an unsupported combo — including tasks whose default
  // run config has tools — skips straight to the manual builder.
  // replaceState keeps the skipped screen out of back-button history.
  onMount(async () => {
    if (!spec_type || !judge) {
      goto(`/specs/${project_id}/${task_id}/select_template`, {
        replaceState: true,
      })
      return
    }
    if (!copilot_supported(spec_type, judge)) {
      goto(spec_builder_url(project_id, task_id, spec_type, "manual", judge), {
        replaceState: true,
      })
      return
    }
    try {
      const task = await load_task(project_id, task_id)
      if (!task) {
        throw new Error("Failed to load task")
      }
      const has_tools = await checkDefaultRunConfigHasTools(project_id, task)
      if (has_tools) {
        goto(
          spec_builder_url(project_id, task_id, spec_type, "manual", judge),
          { replaceState: true },
        )
        return
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  })

  function proceed_manually() {
    if (!spec_type || !judge) return
    goto(spec_builder_url(project_id, task_id, spec_type, "manual", judge))
  }

  // Kiln Pro needs an account. If one is already connected, skip the connect
  // page entirely; otherwise send them through it and it returns to this
  // flow's next step (the spec builder in pro mode) once they're connected.
  async function proceed_with_kiln_pro() {
    if (!spec_type || !judge) return
    error = null
    connecting_pro = true
    try {
      const connected = await checkKilnCopilotAvailable()
      if (connected) {
        goto(spec_builder_url(project_id, task_id, spec_type, "pro", judge))
      } else {
        const params = new URLSearchParams({ type: spec_type, judge })
        goto(`/specs/pro_auth?${params.toString()}`)
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      connecting_pro = false
    }
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Eval"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/evals-and-specs"
    breadcrumbs={[
      {
        label: "Evals",
        href: `/specs/${project_id}/${task_id}`,
      },
      {
        label: "Eval Types",
        href: `/specs/${project_id}/${task_id}/select_template`,
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
      <div class="my-4 max-w-[680px] mx-auto">
        <div class="font-medium text-xl text-center">
          Choose your Eval Creation Workflow
        </div>
        <div class="overflow-x-auto">
          <table class="table w-full mt-4">
            <colgroup>
              <col class="w-[50%]" />
              <col class="w-[25%]" />
              <col class="w-[25%]" />
            </colgroup>
            <thead>
              <tr class="border-b-0">
                <th></th>
                <th class="text-center text-lg">Manual</th>
                <th class="text-center text-lg">
                  <div class="flex items-center justify-center gap-2">
                    <img
                      src="/images/animated_logo.svg"
                      alt="Kiln Eval Builder"
                      class="size-4"
                    />
                    <span>Kiln Eval Builder</span>
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
                <td class="text-center">30 min</td>
                <td class="text-center border-l">5 min</td>
              </tr>
              <tr class="border-b">
                <th class="font-bold text-xs text-base-content/60"
                  >Kiln Account</th
                >
                <td class="text-center">Optional</td>
                <td class="text-center border-l">Required</td>
              </tr>
              <tr>
                <th></th>
                <td class="text-center pt-4">
                  <button
                    class="btn btn-outline btn-sm whitespace-nowrap"
                    disabled={connecting_pro}
                    on:click={proceed_manually}
                  >
                    Create Manually
                  </button>
                </td>
                <td class="text-center pt-4">
                  <button
                    class="btn btn-primary btn-sm whitespace-nowrap"
                    disabled={loading || connecting_pro}
                    on:click={proceed_with_kiln_pro}
                  >
                    {#if connecting_pro}
                      <span class="loading loading-spinner loading-xs"></span>
                    {/if}
                    Use Kiln Pro
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

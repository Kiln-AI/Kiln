<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"
  import { agentInfo } from "$lib/agent"
  import posthog from "posthog-js"

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!
  $: agentInfo.set({
    name: "Choose Data Guide Workflow",
    description: `Choose between manual and Kiln Pro Data Guide creation for project ${project_id}, task ${task_id}.`,
  })

  function pick_manual() {
    posthog.capture("data_guide_chooser_picked", { choice: "manual" })
    goto(`/generate/${project_id}/${task_id}/data_guide_setup`)
  }

  function pick_kiln_pro() {
    posthog.capture("data_guide_chooser_picked", { choice: "kiln_pro" })
    goto(`/generate/pro_auth`)
  }
</script>

<div class="max-w-[900px]">
  <AppPage
    title="Create Data Guide"
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/synthetic-data-generation"
    breadcrumbs={[
      {
        label: "Synthetic Data Generation",
        href: `/generate/${project_id}/${task_id}/synth?session_continued=true`,
        replace_state: true,
      },
    ]}
  >
    <div class="my-4 max-w-[680px] mx-auto">
      <div class="font-medium text-xl text-center">
        Choose your Data Guide Workflow
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
                    alt="Kiln Pro"
                    class="size-4"
                  />
                  <span>Kiln Pro</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th class="font-bold text-xs text-gray-500">Document Upload</th>
              <td class="text-center">—</td>
              <td class="text-center border-l">Supported</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500">Guide Authoring</th>
              <td class="text-center">Manual</td>
              <td class="text-center border-l">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500"
                >Input Pattern Discovery</th
              >
              <td class="text-center">Manual</td>
              <td class="text-center border-l">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500"
                >Style & Constraint Extraction</th
              >
              <td class="text-center">Manual</td>
              <td class="text-center border-l">Automatic</td>
            </tr>
            <tr>
              <th class="font-bold text-xs text-gray-500">Approx. Effort</th>
              <td class="text-center">~30 min</td>
              <td class="text-center border-l">~5 min</td>
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
                  on:click={pick_manual}
                >
                  Create Manually
                </button>
              </td>
              <td class="text-center pt-4">
                <button
                  class="btn btn-primary btn-sm whitespace-nowrap"
                  on:click={pick_kiln_pro}
                >
                  Use Kiln Pro
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </AppPage>
</div>

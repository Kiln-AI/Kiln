<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import AppPage from "../../../../app_page.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

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
              <th class="font-bold text-xs text-gray-500">Eval Data Creation</th
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
              <button
                class="btn btn-primary btn-sm"
                on:click={() =>
                  goto(`/specs/create_new_spec`, {
                    replaceState: true,
                  })}
              >
                Connect Kiln Copilot
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </AppPage>
</div>

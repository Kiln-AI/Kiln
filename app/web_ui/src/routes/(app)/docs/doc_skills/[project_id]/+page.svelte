<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import { onMount } from "svelte"
  import { base_url } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import EmptyDocSkillsIntro from "./empty_doc_skills_intro.svelte"
  import TableDocSkillRow from "./table_doc_skill_row.svelte"
  import { agentInfo } from "$lib/agent"
  import type { DocSkillResponse } from "../doc_skill_types"

  $: project_id = $page.params.project_id!
  $: agentInfo.set({
    name: "Doc Skills",
    description: `List of Doc Skill configurations for project ID ${project_id}. Shows available document skills.`,
  })

  let error: KilnError | null = null
  let loading = true
  let all_doc_skills: DocSkillResponse[] = []

  $: active_doc_skills = all_doc_skills
    .filter((ds) => !ds.is_archived)
    .sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() -
        new Date(a.created_at || 0).getTime(),
    )

  $: archived_doc_skills = all_doc_skills
    .filter((ds) => ds.is_archived)
    .sort(
      (a, b) =>
        new Date(b.created_at || 0).getTime() -
        new Date(a.created_at || 0).getTime(),
    )

  onMount(async () => {
    await load_doc_skills()
  })

  async function load_doc_skills() {
    try {
      loading = true
      error = null

      const response = await fetch(
        `${base_url}/api/projects/${project_id}/doc_skills`,
      )

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(
          body?.detail || `Failed to load doc skills (${response.status})`,
        )
      }

      all_doc_skills = await response.json()
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Doc Skills"
    subtitle="Convert your documents into agent skills."
    no_y_padding={!!(all_doc_skills && all_doc_skills.length === 0 && !loading)}
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      { label: "Docs & Search", href: `/docs/${project_id}` },
    ]}
    action_buttons={all_doc_skills.length === 0 && !loading
      ? []
      : [
          {
            label: "New Doc Skill",
            primary: true,
            href: `/docs/doc_skills/${project_id}/add_doc_skill`,
          },
        ]}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Doc Skills</div>
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else if all_doc_skills.length === 0}
      <div class="flex flex-col items-center justify-center min-h-[50vh]">
        <EmptyDocSkillsIntro {project_id} />
      </div>
    {:else}
      <div class="my-4">
        <div class="overflow-x-auto rounded-lg border">
          <table class="table table-fixed">
            <thead>
              <tr>
                <th class="w-[300px]">Details</th>
                <th class="w-[300px]">Skill Name</th>
                <th class="w-[300px]">Status</th>
              </tr>
            </thead>
            <tbody>
              {#each active_doc_skills as doc_skill}
                <TableDocSkillRow {doc_skill} {project_id} />
              {/each}
              {#if archived_doc_skills.length > 0}
                <tr>
                  <td
                    colspan="3"
                    class="bg-base-200 text-xs font-semibold uppercase tracking-wide text-gray-500 px-4 py-2"
                  >
                    Archived
                  </td>
                </tr>
                {#each archived_doc_skills as doc_skill}
                  <TableDocSkillRow {doc_skill} {project_id} />
                {/each}
              {/if}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"
  import type { Skill } from "$lib/types"

  $: project_id = $page.params.project_id!

  let skills: Skill[] = []
  let loading = true
  let error: KilnError | null = null

  onMount(async () => {
    await fetch_skills()
  })

  async function fetch_skills() {
    try {
      error = null
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/skills",
        {
          params: { path: { project_id } },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      skills = data
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  $: sorted_skills =
    skills
      .slice()
      .sort(
        (a, b) =>
          new Date(b.created_at ?? "").getTime() -
          new Date(a.created_at ?? "").getTime(),
      ) || []
  $: active_skills = sorted_skills.filter((s) => !s.is_archived)
  $: archived_skills = sorted_skills.filter((s) => s.is_archived)
</script>

{#if !loading && skills.length === 0}
  <div class="flex flex-col items-center justify-center min-h-[60vh]">
    <Intro
      title="Agent Skills"
      description_paragraphs={[
        "Skills are reusable instructions that help agents perform specific tasks.",
        "Add skills to give your agents domain knowledge, workflows, and guidelines. Agents load skills on demand — keeping context focused and efficient.",
      ]}
      action_buttons={[
        {
          label: "Add Skill",
          href: `/settings/manage_skills/${project_id}/create`,
          is_primary: true,
        },
      ]}
    />
  </div>
{:else}
  <div class="max-w-[1400px]">
    <!-- TODO: Read the Docs link -->
    <AppPage
      title="Manage Skills"
      subtitle="Reusable instructions for your agents, loaded into context only when needed."
      sub_subtitle="Read the Docs"
      sub_subtitle_link=""
      breadcrumbs={[{ label: "Settings", href: `/settings` }]}
      action_buttons={[
        {
          label: "Add Skill",
          href: `/settings/manage_skills/${project_id}/create`,
          primary: true,
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
          <div class="font-medium">Error Loading Skills</div>
          <div class="text-error text-sm">
            {error.getMessage() || "An unknown error occurred"}
          </div>
        </div>
      {:else}
        <div class="overflow-x-auto rounded-lg border mt-4">
          <table class="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Created At</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {#each active_skills as skill}
                <tr
                  class="hover:bg-base-200 cursor-pointer"
                  on:click={() =>
                    goto(`/settings/manage_skills/${project_id}/${skill.id}`)}
                  on:keydown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      goto(`/settings/manage_skills/${project_id}/${skill.id}`)
                    }
                  }}
                  role="button"
                  tabindex="0"
                >
                  <td class="font-medium">{skill.name}</td>
                  <td class="text-sm max-w-[400px] truncate"
                    >{skill.description}</td
                  >
                  <td class="text-sm whitespace-nowrap"
                    >{formatDate(skill.created_at)}</td
                  >
                  <td class="text-sm">
                    <Warning
                      warning_message="Active"
                      warning_color="success"
                      warning_icon="check"
                      tight={true}
                    />
                  </td>
                </tr>
              {/each}
              {#each archived_skills as skill}
                <tr
                  class="hover:bg-base-200 cursor-pointer opacity-60"
                  on:click={() =>
                    goto(`/settings/manage_skills/${project_id}/${skill.id}`)}
                  on:keydown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault()
                      goto(`/settings/manage_skills/${project_id}/${skill.id}`)
                    }
                  }}
                  role="button"
                  tabindex="0"
                >
                  <td class="font-medium">{skill.name}</td>
                  <td class="text-sm max-w-[400px] truncate"
                    >{skill.description}</td
                  >
                  <td class="text-sm whitespace-nowrap"
                    >{formatDate(skill.created_at)}</td
                  >
                  <td class="text-sm">
                    <Warning
                      warning_message="Archived"
                      warning_color="warning"
                      tight={true}
                    />
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </AppPage>
  </div>
{/if}

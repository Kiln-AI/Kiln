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

  $: sorted_skills = skills
    .slice()
    .sort(
      (a, b) =>
        (b.created_at ? new Date(b.created_at).getTime() : 0) -
        (a.created_at ? new Date(a.created_at).getTime() : 0),
    )
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Manage Skills"
    subtitle="Reusable instructions for your agents, loaded into context only when needed."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/skills"
    breadcrumbs={[{ label: "Settings", href: `/settings` }]}
    action_buttons={!loading && skills.length === 0
      ? []
      : [
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
    {:else if !loading && skills.length === 0}
      <div class="flex flex-col items-center justify-center min-h-[60vh]">
        <Intro
          title="Extend your agent with Skills"
          align_title_left={true}
          description_paragraphs={[
            "Skills provide domain knowledge and reusable workflows.",
            "They load on demand so your agent stays focused and efficient.",
          ]}
          action_buttons={[
            {
              label: "Add Skill",
              href: `/settings/manage_skills/${project_id}/create`,
              is_primary: true,
            },
            {
              label: "Docs & Guide",
              href: "https://docs.kiln.tech/docs/skills",
              is_primary: false,
              new_tab: true,
            },
          ]}
        >
          <div slot="icon">
            <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
            <svg
              class="w-12 h-12"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M4 6V19C4 20.6569 5.34315 22 7 22H17C18.6569 22 20 20.6569 20 19V9C20 7.34315 18.6569 6 17 6H4ZM4 6V5"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <path
                d="M18 6.00002V6.75002H18.75V6.00002H18ZM15.7172 2.32614L15.6111 1.58368L15.7172 2.32614ZM4.91959 3.86865L4.81353 3.12619H4.81353L4.91959 3.86865ZM5.07107 6.75002H18V5.25002H5.07107V6.75002ZM18.75 6.00002V4.30604H17.25V6.00002H18.75ZM15.6111 1.58368L4.81353 3.12619L5.02566 4.61111L15.8232 3.0686L15.6111 1.58368ZM4.81353 3.12619C3.91638 3.25435 3.25 4.0227 3.25 4.92895H4.75C4.75 4.76917 4.86749 4.63371 5.02566 4.61111L4.81353 3.12619ZM18.75 4.30604C18.75 2.63253 17.2678 1.34701 15.6111 1.58368L15.8232 3.0686C16.5763 2.96103 17.25 3.54535 17.25 4.30604H18.75ZM5.07107 5.25002C4.89375 5.25002 4.75 5.10627 4.75 4.92895H3.25C3.25 5.9347 4.06532 6.75002 5.07107 6.75002V5.25002Z"
                fill="currentColor"
              />
              <path
                d="M8 12H16"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M8 15.5H13.5"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </div>
        </Intro>
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
            {#each sorted_skills as skill}
              <tr
                class="hover:bg-base-200 cursor-pointer"
                class:opacity-60={skill.is_archived}
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
                  {#if skill.is_archived}
                    <Warning
                      warning_message="Archived"
                      warning_color="warning"
                      tight={true}
                    />
                  {:else}
                    <Warning
                      warning_message="Active"
                      warning_color="success"
                      warning_icon="check"
                      tight={true}
                    />
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </AppPage>
</div>

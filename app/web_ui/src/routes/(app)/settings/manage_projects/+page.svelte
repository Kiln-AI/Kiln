<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { projects, load_projects, current_project } from "$lib/stores"
  import type { Project } from "$lib/types"
  import { client } from "$lib/api_client"

  async function remove_project(project: Project) {
    try {
      if (!project.id) {
        throw new Error("Project ID is required")
      }
      if (
        confirm(
          `Are you sure you want to remove the project "${project.name}"?\n\nThis will remove it from the UI, but won't delete files from your disk.`,
        )
      ) {
        const {
          error, // only present if 4XX or 5XX response
        } = await client.DELETE("/api/projects/{project_id}", {
          params: {
            path: {
              project_id: project.id,
            },
          },
        })
        if (error) {
          throw error
        }
        await load_projects()
      }
    } catch (e) {
      alert("Failed to remove project.\n\nReason: " + e)
    }
  }
</script>

<AppPage
  title="Manage Projects"
  subtitle="Add or remove projects"
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
  action_buttons={[
    { label: "Create Project", href: "/settings/create_project" },
    {
      label: "Import Project",
      href: "/settings/create_project?import=true",
    },
  ]}
>
  {#if $projects == null}
    <div class=" mx-auto py-8 px-24">
      <span class="loading loading-spinner loading-md"></span>
    </div>
  {:else if $projects.error}
    <div class="p-16">{$projects.error}</div>
  {:else if $projects.projects.length == 0}
    <div class="p-16">No projects found</div>
  {:else}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(22rem,1fr))] gap-4">
      {#each $projects.projects as project}
        <div
          class="card card-bordered border-gray-500 shadow-md py-4 px-6 min-h-60"
        >
          <div class="flex flex-col h-full">
            <div class="grow">
              <div class="font-medium flex flex-row gap-2">
                <div class="grow">{project.name}</div>
                {#if project.id == $current_project?.id}
                  <span class="badge badge-primary">Current</span>
                {/if}
              </div>
              {#if project.description && project.description.length > 0}
                <div class="text-sm">
                  {project.description}
                </div>
              {/if}
              <div class="text-xs text-gray-500 mt-1 break-all">
                {project.path}
              </div>
            </div>
            <div
              class="grid grid-cols-[repeat(auto-fill,minmax(6rem,1fr))] gap-2 w-full mt-6"
            >
              <a
                href={`/settings/create_task/${project.id}`}
                class="btn btn-xs w-full"
              >
                Add Task
              </a>
              <a
                href={`/settings/edit_project/${project.id}`}
                class="btn btn-xs w-full"
              >
                Edit Project
              </a>
              <button
                on:click={() => remove_project(project)}
                class="btn btn-xs w-full"
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</AppPage>

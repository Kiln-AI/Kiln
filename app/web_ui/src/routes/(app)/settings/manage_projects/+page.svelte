<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { projects, load_projects, current_project } from "$lib/stores"
  import type { Project } from "$lib/types"
  import { client } from "$lib/api_client"
  import { _ } from "svelte-i18n"

  async function remove_project(project: Project) {
    try {
      if (!project.id) {
        throw new Error("Project ID is required")
      }
      if (
        confirm(
          $_("project.remove_project_confirm", {
            values: { name: project.name },
          }),
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
      alert(
        $_("project.failed_to_remove_project", {
          values: { error: String(e) },
        }),
      )
    }
  }
</script>

<AppPage
  title={$_("project.manage_projects")}
  subtitle={$_("project.manage_projects_subtitle")}
  action_buttons={[
    { label: $_("project.create_project"), href: "/settings/create_project" },
    {
      label: $_("project.import_project"),
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
    <div class="p-16">{$_("project.no_projects_found")}</div>
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
                  <span class="badge badge-primary"
                    >{$_("project.current")}</span
                  >
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
                {$_("project.add_task")}
              </a>
              <a
                href={`/settings/edit_project/${project.id}`}
                class="btn btn-xs w-full"
              >
                {$_("project.edit_project")}
              </a>
              <button
                on:click={() => remove_project(project)}
                class="btn btn-xs w-full"
              >
                {$_("common.remove")}
              </button>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</AppPage>

<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { projects, load_projects } from "$lib/stores"
  import type { Project } from "$lib/types"
  import { client } from "$lib/api_client"
  import TableButton from "../../generate/[project_id]/[task_id]/table_button.svelte"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"

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

  async function open_project_folder(project: Project) {
    if (!project.id) {
      throw new Error("Project ID is required")
    }
    try {
      const { error } = await client.POST(
        "/api/open_project_folder/{project_id}",
        {
          params: {
            path: { project_id: project.id },
          },
        },
      )
      if (error) {
        throw error
      }
    } catch (e) {
      alert("Failed to open project folder.\n\nReason: " + e)
    }
  }
</script>

<AppPage
  title="Manage Projects"
  subtitle="Add or remove projects"
  limit_max_width={true}
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
    <div class="rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th>Project Name</th>
            <th>Description</th>
            <th>Created At</th>
            <th>Path</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each $projects.projects as project}
            {@const path = project.path
              ? project.path
                  .replace("/project.kiln", "")
                  .replace("\\project.kiln", "")
              : "Unknown"}
            <tr>
              <td class="font-medium">{project.name}</td>
              <td>{project.description}</td>
              <td>
                {formatDate(project.created_at)}
              </td>
              <td>
                <button
                  class="link text-gray-500"
                  on:click={() => open_project_folder(project)}
                >
                  {path.length > 64 ? path.slice(0, 64) + "..." : path}
                </button>
              </td>
              <td class="p-0">
                <div class="dropdown dropdown-end dropdown-hover">
                  <TableButton />
                  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
                  <ul
                    tabindex="0"
                    class="dropdown-content menu bg-base-100 rounded-box z-[1] w-52 p-2 shadow"
                  >
                    <li>
                      <button
                        on:click={() =>
                          goto(`/settings/create_task/${project.id}`)}
                        >Add Task</button
                      >
                    </li>
                    <li>
                      <button
                        on:click={() =>
                          goto(`/settings/edit_project/${project.id}`)}
                        >Edit Project</button
                      >
                    </li>
                    <li>
                      <button on:click={() => remove_project(project)}
                        >Remove Project</button
                      >
                    </li>
                    <li>
                      <button on:click={() => open_project_folder(project)}
                        >Open Folder</button
                      >
                    </li>
                  </ul>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</AppPage>

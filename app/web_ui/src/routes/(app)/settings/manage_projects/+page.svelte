<script lang="ts">
  import AppPage from "../../app_page.svelte"
  import { projects, load_projects } from "$lib/stores"
  import { agentInfo } from "$lib/agent"
  import type { Project } from "$lib/types"
  import { client } from "$lib/api_client"
  import TableActionMenu from "$lib/ui/table_action_menu.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"
  import { getConfig } from "$lib/git_sync/api"

  let git_urls: Record<string, string | null> = {}

  async function load_git_url(project_id: string) {
    if (project_id in git_urls) return
    git_urls = { ...git_urls, [project_id]: null }
    try {
      const config = await getConfig(project_id)
      if (config?.git_url) {
        git_urls = { ...git_urls, [project_id]: config.git_url }
      }
    } catch {
      // Non-fatal: tooltip will just show without URL
    }
  }

  $: if ($projects?.projects) {
    for (const project of $projects.projects) {
      if (project.id && is_git_managed_project(project)) {
        load_git_url(project.id)
      }
    }
  }

  function is_git_managed_project(project: Project): boolean {
    return project.path
      ? project.path.includes("Kiln Projects/.git-projects/") ||
          project.path.includes("Kiln Projects\\.git-projects\\")
      : false
  }

  agentInfo.set({
    name: "Manage Projects",
    description:
      "Manage all projects. Create new projects, edit existing ones, or remove projects.",
  })

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
        } = await client.DELETE("/api/delete_project/{project_id}", {
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
    { label: "Import Project", href: "/settings/import_project" },
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
            {@const is_git_managed = is_git_managed_project(project)}
            <tr>
              <td class="font-medium">{project.name}</td>
              <td>{project.description || "N/A"}</td>
              <td>
                {formatDate(project.created_at)}
              </td>
              <td>
                {#if is_git_managed}
                  {@const url = project.id ? git_urls[project.id] : undefined}
                  <span class="text-gray-500 inline-flex items-center gap-0.5"
                    >Git Auto Sync<InfoTooltip
                      tooltip_text={url
                        ? `This project is automatically synced to the git repository ${url}`
                        : "This project is automatically synced to a git repository"}
                      no_pad
                    /></span
                  >
                {:else}
                  <button
                    class="link text-gray-500"
                    on:click={() => open_project_folder(project)}
                  >
                    {path.length > 64 ? path.slice(0, 64) + "..." : path}
                  </button>
                {/if}
              </td>
              <td class="p-0">
                <TableActionMenu
                  items={[
                    {
                      label: "Add Task",
                      onclick: () =>
                        goto(`/settings/create_task/${project.id}`),
                    },
                    {
                      label: "Edit Project",
                      onclick: () =>
                        goto(`/settings/edit_project/${project.id}`),
                    },
                    {
                      label: "Remove Project",
                      onclick: () => remove_project(project),
                    },
                    ...(!is_git_managed
                      ? [
                          {
                            label: "Open Folder",
                            onclick: () => open_project_folder(project),
                          },
                        ]
                      : []),
                  ]}
                />
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</AppPage>

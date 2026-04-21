<script lang="ts">
  import AppPage from "../app_page.svelte"
  import {
    ui_state,
    current_project,
    current_task,
    projects,
  } from "$lib/stores"
  import KilnSettingsRow from "$lib/ui/kiln_settings_row.svelte"
  import { view_logs } from "$lib/utils/logs"
  import { agentInfo } from "$lib/agent"
  import { update_info, app_version } from "$lib/utils/update"
  import ArrowUpIcon from "$lib/ui/icons/arrow_up_icon.svelte"
  import EditIcon from "$lib/ui/icons/edit_icon.svelte"
  import FolderIcon from "$lib/ui/icons/folder_icon.svelte"
  import DatabaseIcon from "$lib/ui/icons/database_icon.svelte"
  import KeyIcon from "$lib/ui/icons/key_icon.svelte"
  import CubeIcon from "$lib/ui/icons/cube_icon.svelte"
  import TerminalIcon from "$lib/ui/icons/terminal_icon.svelte"
  import RefreshIcon from "$lib/ui/icons/refresh_icon.svelte"
  import BookIcon from "$lib/ui/icons/book_icon.svelte"
  import ShieldIcon from "$lib/ui/icons/shield_icon.svelte"

  agentInfo.set({
    name: "Settings",
    description:
      "Main settings page with options for editing current workspace, managing AI providers and custom models, managing projects, viewing logs, and checking for updates.",
  })

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type IconComponent = any

  type SettingsRow = {
    label: string
    icon: IconComponent
    detail: string | undefined
    href: string | undefined
    on_click: (() => void) | undefined
    is_external: boolean | undefined
    status: "warn" | undefined
  }

  type SettingsSection = {
    title: string
    rows: Array<SettingsRow>
  }

  $: project_count = $projects?.projects?.length ?? 0

  $: sections = [
    {
      title: "Workspace",
      rows: [
        {
          label: "Edit Current Task",
          icon: EditIcon,
          detail: $current_task?.name,
          href: `/settings/edit_task/${$ui_state?.current_project_id}/${$ui_state?.current_task_id}`,
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
        {
          label: "Edit Current Project",
          icon: FolderIcon,
          detail: $current_project?.name,
          href: "/settings/edit_project/" + $ui_state.current_project_id,
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
        {
          label: "Manage Projects",
          icon: DatabaseIcon,
          detail:
            project_count > 0
              ? `${project_count} project${project_count === 1 ? "" : "s"}`
              : undefined,
          href: "/settings/manage_projects",
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
      ],
    },
    {
      title: "Models & Providers",
      rows: [
        {
          label: "AI Providers",
          icon: KeyIcon,
          detail: "Manage connected providers",
          href: "/settings/providers",
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
        {
          label: "Custom Models",
          icon: CubeIcon,
          detail: "Add or remove custom models",
          href: "/settings/providers/add_models",
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
      ],
    },
    {
      title: "Application",
      rows: [
        {
          label: "Application Logs",
          icon: TerminalIcon,
          detail: "LLM calls and application events",
          href: undefined,
          on_click: view_logs,
          is_external: undefined,
          status: undefined,
        },
        {
          label: "Check for Update",
          icon: RefreshIcon,
          detail: `Kiln ${app_version}`,
          href: "/settings/check_for_update",
          on_click: undefined,
          is_external: undefined,
          status: undefined,
        },
      ],
    },
    {
      title: "About",
      rows: [
        {
          label: "Docs & Getting Started",
          icon: BookIcon,
          detail: "docs.kiln.tech",
          href: "https://docs.kiln.tech",
          on_click: undefined,
          is_external: true,
          status: undefined,
        },
        {
          label: "License Agreement",
          icon: ShieldIcon,
          detail: "EULA",
          href: "https://github.com/Kiln-AI/Kiln/blob/main/app/EULA.md",
          on_click: undefined,
          is_external: true,
          status: undefined,
        },
      ],
    },
  ] satisfies Array<SettingsSection>
</script>

<AppPage title="Settings" no_y_padding>
  <div class="max-w-3xl mt-8 space-y-6">
    {#if $update_info.update_result?.has_update}
      <div
        class="card card-bordered border-primary/30 bg-primary/5 shadow-sm rounded-md"
        data-testid="update-available-callout"
      >
        <div class="flex flex-row items-center gap-4 p-4">
          <div
            class="flex-shrink-0 w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center"
          >
            <div class="w-5 h-5">
              <ArrowUpIcon />
            </div>
          </div>
          <div class="flex-grow min-w-0">
            <div class="font-medium text-primary">Update Available</div>
            <div class="text-sm font-light text-gray-500">
              A new version of Kiln is ready to install.
            </div>
          </div>
          <a
            href="/settings/check_for_update"
            class="btn btn-primary btn-sm flex-shrink-0"
          >
            View Update
          </a>
        </div>
      </div>
    {/if}

    {#each sections as section}
      <div>
        <h2
          class="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-500"
        >
          {section.title}
        </h2>
        <div class="bg-white border border-gray-200 rounded-lg overflow-hidden">
          {#each section.rows as row, i}
            <KilnSettingsRow
              label={row.label}
              detail={row.detail}
              href={row.href}
              on_click={row.on_click}
              is_external={row.is_external ?? false}
              status={row.status}
              is_last={i === section.rows.length - 1}
            >
              <svelte:fragment slot="icon">
                <svelte:component this={row.icon} />
              </svelte:fragment>
            </KilnSettingsRow>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</AppPage>

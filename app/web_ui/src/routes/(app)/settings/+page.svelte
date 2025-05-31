<script lang="ts">
  import AppPage from "../app_page.svelte"
  import { ui_state } from "$lib/stores"
  import { _ } from "svelte-i18n"
  import LanguageSwitcher from "$lib/ui/language_switcher.svelte"

  let sections = [
    {
      name: $_("settings.edit_task"),
      description: $_("settings.edit_task_description"),
      button_text: $_("settings.edit_current_task"),
      href: `/settings/edit_task/${$ui_state?.current_project_id}/${$ui_state?.current_task_id}`,
    },
    {
      name: $_("settings.ai_providers"),
      description: $_("settings.ai_providers_description"),
      href: "/settings/providers",
      button_text: $_("settings.manage_providers"),
    },
    {
      name: $_("project.manage_projects"),
      description: $_("settings.manage_projects_description"),
      href: "/settings/manage_projects",
      button_text: $_("project.manage_projects"),
    },
    {
      name: $_("project.edit_project"),
      description: $_("settings.edit_project_description"),
      button_text: $_("settings.edit_current_project"),
      href: "/settings/edit_project/" + $ui_state.current_project_id,
    },
    {
      name: $_("settings.app_updates"),
      description: $_("settings.app_updates_description"),
      href: "/settings/check_for_update",
      button_text: $_("settings.check_for_update"),
    },
    {
      name: $_("settings.replay_introduction"),
      description: $_("settings.replay_intro_description"),
      href: "/settings/intro",
      button_text: $_("settings.play_intro"),
    },
    {
      name: $_("settings.license"),
      description: $_("settings.license_description"),
      href: "https://github.com/Kiln-AI/Kiln/blob/main/app/EULA.md",
      button_text: $_("settings.view_eula"),
      is_external: true,
    },
  ]
</script>

<AppPage title={$_("settings.title")}>
  <div class="flex flex-col gap-8 max-w-[700px] mt-16">
    {#each sections as section}
      <div class="flex flex-col md:flex-row gap-4 md:items-center">
        <div class="grow">
          <h3 class="font-medium">{section.name}</h3>
          <p class="text-sm text-gray-500">{section.description}</p>
        </div>
        <a
          href={section.href}
          class="btn"
          style="min-width: 14rem"
          target={section.is_external ? "_blank" : "_self"}
        >
          {section.button_text}
        </a>
      </div>
    {/each}

    <!-- 语言设置部分 -->
    <div class="flex flex-col md:flex-row gap-4 md:items-center">
      <div class="grow">
        <h3 class="font-medium">{$_("settings.language")}</h3>
        <p class="text-sm text-gray-500">
          {$_("settings.language_description")}
        </p>
      </div>
      <div style="min-width: 14rem" class="flex justify-end">
        <LanguageSwitcher />
      </div>
    </div>
  </div>
</AppPage>

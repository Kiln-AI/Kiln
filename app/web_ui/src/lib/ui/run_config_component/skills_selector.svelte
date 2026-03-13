<script lang="ts">
  import FormElement from "$lib/utils/form_element.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"
  import { available_tools, load_available_tools } from "$lib/stores"
  import { onMount } from "svelte"
  import type { ToolSetApiDescription } from "$lib/types"
  import {
    skills_store,
    skills_store_initialized,
  } from "$lib/stores/skills_store"
  import { goto } from "$app/navigation"
  import type { SkillsSelectorSettings } from "./skills_selector_settings"

  export let project_id: string
  export let task_id: string | null = null
  export let skills: string[] = []
  export let settings: Partial<SkillsSelectorSettings> = {}

  let default_settings: SkillsSelectorSettings = {
    mandatory_skills: null,
    description: undefined,
    info_description:
      "Select skills available to the agent. Skills are reusable sub-tasks the agent can delegate to.",
    hide_info_description: false,
    disabled: false,
    empty_label: "None",
    optional: true,
  }
  $: resolved = { ...default_settings, ...settings }

  const CREATE_NEW_SKILL = "__create_new_skill__"

  let skills_store_loaded_task_id: string | null = null

  onMount(async () => {
    await load_skills(project_id, task_id)
  })

  $: load_skills(project_id, task_id)

  async function load_skills(project_id: string, task_id: string | null) {
    load_available_tools(project_id)

    if (!task_id) {
      skills = resolved.mandatory_skills || []
      skills_store_loaded_task_id = null
    } else if (task_id !== skills_store_loaded_task_id) {
      await skills_store_initialized
      const existing_skills =
        $skills_store.selected_skill_ids_by_task_id[task_id] || []
      const combined = [
        ...(resolved.mandatory_skills || []),
        ...existing_skills,
      ]
      skills = [...new Set(combined)]
      skills_store_loaded_task_id = task_id
    }
  }

  $: if (task_id && skills && skills_store_loaded_task_id === task_id) {
    const persistable = skills.filter((id) => id !== CREATE_NEW_SKILL)
    skills_store.update((state) => ({
      ...state,
      selected_skill_ids_by_task_id: {
        ...state.selected_skill_ids_by_task_id,
        [task_id]: persistable,
      },
    }))
  }

  $: handle_sentinel_selection(skills)

  function handle_sentinel_selection(current_skills: string[]) {
    if (current_skills.includes(CREATE_NEW_SKILL)) {
      skills = current_skills.filter((v) => v !== CREATE_NEW_SKILL)
      goto(`/settings/manage_skills/${project_id}/create`)
    }
  }

  $: filter_unavailable_skills($available_tools[project_id], skills)

  function filter_unavailable_skills(
    available_tool_sets: ToolSetApiDescription[] | undefined,
    current_skills: string[],
  ) {
    if (
      !available_tool_sets ||
      !project_id ||
      !current_skills ||
      current_skills.length === 0
    ) {
      return
    }

    const available_skill_ids = new Set(
      available_tool_sets
        .filter((ts) => ts.type === "skill")
        .flatMap((ts) => ts.tools.map((t) => t.id)),
    )

    const unavailable = current_skills.filter(
      (id) => !available_skill_ids.has(id),
    )

    if (unavailable.length > 0) {
      console.warn("Removing unavailable skills:", unavailable)
      skills = current_skills.filter((id) => available_skill_ids.has(id))
    }
  }

  function get_skill_options(
    available_tool_sets: ToolSetApiDescription[] | undefined,
  ): OptionGroup[] {
    let option_groups: OptionGroup[] = []

    option_groups.push({
      label: "",
      options: [
        {
          value: CREATE_NEW_SKILL,
          label: "New Skill",
          badge: "＋",
          badge_color: "primary",
          hide_check: true,
        },
      ],
    })

    if (!available_tool_sets) {
      return option_groups
    }

    const skill_sets = available_tool_sets.filter(
      (ts) => ts.type === "skill" && ts.tools.length > 0,
    )

    if (skill_sets.length > 0) {
      const skill_options = skill_sets.flatMap((ts) =>
        ts.tools.map((tool) => ({
          value: tool.id,
          label: tool.name,
          description: tool.description ? tool.description.trim() : undefined,
          disabled: resolved.mandatory_skills
            ? resolved.mandatory_skills.includes(tool.id)
            : false,
        })),
      )

      option_groups.push({
        label: "Available Skills",
        options: skill_options,
      })
    }

    return option_groups
  }
</script>

<div>
  <FormElement
    id="skills"
    label="Skills"
    description={resolved.description}
    info_description={resolved.hide_info_description
      ? undefined
      : resolved.info_description}
    inputType="multi_select"
    fancy_select_options={get_skill_options($available_tools[project_id])}
    bind:value={skills}
    empty_label={resolved.empty_label ?? default_settings.empty_label}
    empty_state_message={$available_tools[project_id] === undefined
      ? "Loading skills..."
      : "No Skills Available"}
    empty_state_subtitle="New Skill"
    empty_state_link={`/settings/manage_skills/${project_id}/create`}
    disabled={resolved.disabled}
    optional={resolved.optional}
  />
</div>

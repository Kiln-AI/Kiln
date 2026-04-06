<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { client, base_url } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { uncache_available_tools, ui_state } from "$lib/stores"
  import { formatDate } from "$lib/utils/formatters"
  import type { Skill } from "$lib/types"
  import type { UiProperty } from "$lib/ui/property_list"
  import SkillPropertiesDisplay from "../../skill_properties_display.svelte"

  import { agentInfo } from "$lib/agent"
  $: project_id = $page.params.project_id!
  $: skill_id = $page.params.skill_id!
  $: agentInfo.set({
    name: "Skill Detail",
    description: `Skill detail page for skill ID ${skill_id} in project ID ${project_id}.${skill?.name ? ` Skill name: '${skill.name}'.` : ""} Shows skill description, body, and properties.`,
  })

  let skill: Skill | null = null
  let skill_description: string | null = null
  let skill_body: string | null = null
  let loading = true
  let loading_error: KilnError | null = null
  let archive_error: KilnError | null = null

  let doc_skill_source: {
    doc_skill_id: string | null
    doc_skill_name: string | null
  } | null = null

  onMount(async () => {
    await Promise.all([fetch_skill(), fetch_doc_skill_source()])
  })

  // Raw fetch used because this doc_skill_source endpoint isn't in the generated OpenAPI types
  async function fetch_doc_skill_source() {
    try {
      const response = await fetch(
        `${base_url}/api/projects/${project_id}/skills/${skill_id}/doc_skill_source`,
      )
      if (response.ok) {
        doc_skill_source = await response.json()
      }
    } catch {
      // Non-critical — silently ignore
    }
  }

  async function fetch_skill() {
    try {
      loading = true
      loading_error = null
      const params = { path: { project_id, skill_id } }
      const [skill_res, content_res] = await Promise.all([
        client.GET("/api/projects/{project_id}/skills/{skill_id}", { params }),
        client.GET("/api/projects/{project_id}/skills/{skill_id}/content", {
          params,
        }),
      ])
      if (skill_res.error || content_res.error) {
        throw skill_res.error ?? content_res.error
      }
      skill = skill_res.data
      skill_description = skill_res.data?.description ?? null
      skill_body = content_res.data?.body ?? null
    } catch (err) {
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function get_properties(skill: Skill): UiProperty[] {
    const props: UiProperty[] = [
      { name: "ID", value: skill.id ?? "" },
      { name: "Name", value: skill.name },
    ]
    if (skill.created_at) {
      props.push({
        name: "Created At",
        value: formatDate(skill.created_at),
      })
    }
    if (skill.created_by) {
      props.push({ name: "Created By", value: skill.created_by })
    }
    return props
  }

  async function update_archive(is_archived: boolean) {
    try {
      archive_error = null
      const { error: api_error } = await client.PATCH(
        "/api/projects/{project_id}/skills/{skill_id}",
        {
          params: { path: { project_id, skill_id } },
          body: { is_archived },
        },
      )
      if (api_error) {
        throw api_error
      }
      uncache_available_tools(project_id)
    } catch (e) {
      archive_error = createKilnError(e)
    } finally {
      await fetch_skill()
    }
  }

  $: is_archived = skill?.is_archived ?? false
</script>

<div class="max-w-[1400px]">
  <AppPage
    title={`Skill: ${skill?.name || ""}`}
    subtitle="Reusable instructions for your agents, loaded into context only when needed."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/skills"
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      {
        label: "Skills",
        href: `/skills/${project_id}`,
      },
    ]}
    action_buttons={skill && !loading && !loading_error
      ? [
          {
            label: "Clone",
            handler: () => goto(`/skills/${project_id}/clone/${skill_id}`),
          },
          {
            label: is_archived ? "Unarchive" : "Archive",
            handler: () => update_archive(!is_archived),
          },
        ]
      : []}
  >
    {#if archive_error}
      <Warning
        warning_message={archive_error.getMessage() ||
          "An unknown error occurred"}
        large_icon={true}
        warning_color="error"
        outline={true}
      />
    {/if}
    {#if is_archived}
      <Warning
        warning_message="This skill is archived. It will not appear in available skills. You may unarchive it to use it again."
        large_icon={true}
        warning_color="warning"
        outline={true}
      />
    {/if}
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if loading_error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Error Loading Skill</div>
        <div class="text-error text-sm">
          {loading_error.getMessage() || "An unknown error occurred"}
        </div>
        <button
          class="btn btn-primary mt-4"
          on:click={() => goto(`/skills/${project_id}`)}
        >
          Back to Skills
        </button>
      </div>
    {:else if skill}
      {#if doc_skill_source?.doc_skill_id}
        <div
          class="flex items-center gap-2 text-sm text-gray-500 border rounded-lg px-4 py-3 mb-6"
        >
          <span>Created from Documents</span>
          <span class="text-gray-300">|</span>
          <a
            href={`/docs/doc_skills/${project_id}/${doc_skill_source.doc_skill_id}/doc_skill`}
            class="link link-primary"
          >
            {doc_skill_source.doc_skill_name || "View Doc Skill"}
          </a>
        </div>
      {/if}
      <div class="grid grid-cols-1 lg:grid-cols-[1fr,auto] gap-12">
        <div class="grow">
          <SkillPropertiesDisplay
            description={skill_description}
            body={skill_body}
          />
        </div>
        <div class="flex flex-col gap-4 max-w-[400px]">
          <PropertyList properties={get_properties(skill)} title="Properties" />
        </div>
      </div>
    {:else}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="font-medium">Skill Not Found</div>
        <div class="text-gray-500 text-sm">
          The requested skill could not be found.
        </div>
        <button
          class="btn btn-primary mt-4"
          on:click={() => goto(`/skills/${project_id}`)}
        >
          Back to Skills
        </button>
      </div>
    {/if}
  </AppPage>
</div>

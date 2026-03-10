<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { formatDate } from "$lib/utils/formatters"
  import type { Skill } from "$lib/types"
  import type { UiProperty } from "$lib/ui/property_list"

  $: project_id = $page.params.project_id!
  $: skill_id = $page.params.skill_id!

  let skill: Skill | null = null
  let loading = true
  let loading_error: KilnError | null = null
  let archive_error: KilnError | null = null

  onMount(async () => {
    await fetch_skill()
  })

  async function fetch_skill() {
    try {
      loading = true
      loading_error = null
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/skills/{skill_id}",
        {
          params: { path: { project_id, skill_id } },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      skill = data
    } catch (err) {
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  function get_properties(skill: Skill): UiProperty[] {
    const props: UiProperty[] = [
      { name: "Name", value: skill.name },
      { name: "Description", value: skill.description },
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
    } catch (e) {
      archive_error = createKilnError(e)
    } finally {
      await fetch_skill()
    }
  }

  $: is_archived = skill?.is_archived ?? false
</script>

<div class="max-w-[1400px]">
  <!-- TODO: Read the Docs link -->
  <AppPage
    title="Skill"
    subtitle={`Name: ${skill?.name || ""}`}
    sub_subtitle="Read the Docs"
    sub_subtitle_link=""
    breadcrumbs={[
      { label: "Settings", href: `/settings` },
      {
        label: "Manage Skills",
        href: `/settings/manage_skills/${project_id}`,
      },
    ]}
    action_buttons={[
      {
        label: is_archived ? "Unarchive" : "Archive",
        handler: () => update_archive(!is_archived),
      },
    ]}
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
          on:click={() => goto(`/settings/manage_skills/${project_id}`)}
        >
          Back to Skills
        </button>
      </div>
    {:else if skill}
      <div class="grid grid-cols-1 lg:grid-cols-[1fr,auto] gap-12">
        <div class="grow max-w-[900px]">
          <h3 class="text-xl font-bold mb-4">Instructions</h3>
          <div
            class="bg-base-200 rounded-lg p-6 text-sm whitespace-pre-wrap font-mono max-h-[600px] overflow-y-auto"
          >
            {skill.body}
          </div>
        </div>
        <div class="flex flex-col gap-4">
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
          on:click={() => goto(`/settings/manage_skills/${project_id}`)}
        >
          Back to Skills
        </button>
      </div>
    {/if}
  </AppPage>
</div>

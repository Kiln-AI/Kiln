<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { tool_name_validator } from "$lib/utils/input_validators"
  import { uncache_available_tools } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"

  $: project_id = $page.params.project_id!

  let name = ""
  let description = ""
  let body = ""
  let error: KilnError | null = null
  let submitting = false

  async function handleSubmit() {
    try {
      error = null
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/skills",
        {
          params: { path: { project_id } },
          body: { name, description, body },
        },
      )
      if (api_error) {
        throw api_error
      }
      if (data) {
        uncache_available_tools(project_id)
        goto(`/settings/manage_skills/${project_id}`)
      }
    } catch (err) {
      error = createKilnError(err)
    } finally {
      submitting = false
    }
  }
</script>

<div class="max-w-2xl">
  <AppPage
    title="Add Skill"
    subtitle="Add reusable instructions for your agents, loaded into context only when needed."
    sub_subtitle="Read the Docs"
    sub_subtitle_link="https://docs.kiln.tech/docs/skills"
    breadcrumbs={[
      { label: "Settings", href: `/settings` },
      {
        label: "Manage Skills",
        href: `/settings/manage_skills/${project_id}`,
      },
    ]}
  >
    <FormContainer
      submit_label="Add"
      {error}
      on:submit={handleSubmit}
      bind:submitting
    >
      <FormElement
        id="skill_name"
        label="Name"
        description="A unique short identifier for the skill such as 'style_guidelines'."
        info_description="Must be in snake_case format."
        bind:value={name}
        validator={tool_name_validator}
      />
      <FormElement
        id="skill_description"
        label="Description"
        inputType="textarea"
        description="A description of when an agent should use this skill."
        info_description="This is shown to the agent to help it decide when to load the skill. Keep it concise but informative."
        bind:value={description}
        max_length={1024}
      />
      <FormElement
        id="skill_body"
        label="Instructions"
        inputType="textarea"
        height="xl"
        description="The markdown content the agent will read when it loads this skill."
        info_description="Write markdown instructions, examples, workflows, and guidelines. This is only loaded into context when the agent chooses to use the skill."
        bind:value={body}
      />
    </FormContainer>
  </AppPage>
</div>

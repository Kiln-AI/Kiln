<script lang="ts">
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import {
    skill_name_validator,
    normalize_skill_name,
  } from "$lib/utils/input_validators"
  import { uncache_available_tools } from "$lib/stores"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"

  export let project_id: string
  export let skill_id: string | undefined = undefined
  export let clone_mode: boolean = false

  let name = ""
  let description = ""
  let body = ""
  let error: KilnError | null = null
  let submitting = false
  let loading = false
  let loading_error: KilnError | null = null
  let complete = false

  onMount(async () => {
    if (clone_mode && skill_id) {
      await load_skill_for_clone()
    }
  })

  async function load_skill_for_clone() {
    if (!skill_id) {
      loading_error = createKilnError(
        new Error("Skill ID is required for cloning"),
      )
      return
    }
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
      // Pre-fill form with existing skill data
      name = `copy-of-${skill_res.data.name}`
      description = skill_res.data.description
      body = content_res.data?.body ?? ""
    } catch (err) {
      loading_error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function handleSubmit() {
    try {
      error = null
      submitting = true
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
        goto(`/skills/${project_id}/${data.id}`)
      }
    } catch (err) {
      error = createKilnError(err)
    } finally {
      submitting = false
      complete = true
    }
  }

  $: name = normalize_skill_name(name).slice(0, 64)

  $: submit_label = clone_mode ? "Clone" : "Add"

  $: warn_before_unload =
    !complete && (name !== "" || description !== "" || body !== "")
</script>

{#if clone_mode && loading}
  <div class="w-full min-h-[50vh] flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else if clone_mode && loading_error}
  <div class="alert alert-error">
    {loading_error.getMessage() || "An unknown error occurred"}
  </div>
  <button
    class="btn btn-primary mt-4"
    on:click={() => goto(`/skills/${project_id}`)}
  >
    Back to Skills
  </button>
{:else}
  <FormContainer
    {submit_label}
    {error}
    on:submit={handleSubmit}
    bind:submitting
    {warn_before_unload}
  >
    <FormElement
      id="skill_name"
      label="Name"
      description="A unique short identifier for the skill such as 'style-guidelines'."
      info_description="Must be in kebab-case format. Lowercase letters, numbers, and hyphens only."
      bind:value={name}
      validator={skill_name_validator}
      max_length={64}
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
{/if}

<script lang="ts">
  import { goto } from "$app/navigation"
  import { load_projects } from "$lib/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Project } from "$lib/types"
  import { tick } from "svelte"
  import posthog from "posthog-js"

  export let created = false
  export let redirect_on_created: string | null = null
  export let import_link: string

  export let project: Project = {
    v: 1,
    name: "",
    description: "",
  }
  let error: KilnError | null = null
  let submitting = false
  let saved = false

  $: warn_before_unload =
    !saved && [project?.name, project?.description].some((value) => !!value)

  function redirect_to_project(project_id: string) {
    goto(redirect_on_created + "/" + project_id)
  }

  const save_project = async () => {
    try {
      saved = false
      submitting = true
      if (!project?.name) {
        throw new Error("Project name is required")
      }
      let data: Project | undefined = undefined
      let error: unknown | undefined = undefined
      let body = {
        name: project.name,
        description: project.description,
      }
      let create = !project.id
      if (!project.id) {
        const { data: post_data, error: post_error } = await client.POST(
          "/api/project",
          {
            // @ts-expect-error we're missing fields like v1, which have default values
            body,
          },
        )
        data = post_data
        error = post_error
        if (!error) {
          posthog.capture("create_project", {})
        }
      } else {
        const { data: put_data, error: put_error } = await client.PATCH(
          "/api/project/{project_id}",
          {
            params: {
              path: {
                project_id: project.id,
              },
            },
            body,
          },
        )
        data = put_data
        error = put_error
        if (!error) {
          posthog.capture("update_project", {})
        }
      }
      if (error) {
        throw error
      }

      await load_projects()
      error = null
      if (create) {
        created = true
      }
      saved = true
      await tick()
      if (redirect_on_created && data?.id) {
        redirect_to_project(data.id)
        return
      }
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<div class="flex flex-col gap-2 w-full">
  {#if !created}
    <FormContainer
      submit_label={project.id ? "Update Project" : "Create Project"}
      on:submit={save_project}
      bind:warn_before_unload
      bind:submitting
      bind:error
      bind:saved
    >
      <FormElement
        label="Project Name"
        id="project_name"
        inputType="input"
        bind:value={project.name}
        max_length={120}
      />
      <FormElement
        label="Project Description"
        id="project_description"
        inputType="textarea"
        optional={true}
        bind:value={project.description}
      />
    </FormContainer>
    {#if !project.id}
      <p class="mt-4 text-center">
        Or
        <a class="link font-bold" href={import_link}>
          import an existing project
        </a>
      </p>
    {/if}
  {:else if !redirect_on_created}
    <h2 class="text-xl font-medium text-center">Project Created!</h2>
    <p class="text-sm text-center">
      Your new project "{project.name}" has been created.
    </p>
  {/if}
</div>

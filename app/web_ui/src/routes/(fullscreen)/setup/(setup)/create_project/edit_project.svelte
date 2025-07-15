<script lang="ts">
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { load_projects } from "$lib/stores"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import type { Project } from "$lib/types"
  import { onMount, tick } from "svelte"
  import posthog from "posthog-js"

  let importing = false
  onMount(() => {
    importing = $page.url.searchParams.get("import") === "true"
  })

  export let created = false
  // Prevents flash of complete UI if we're going to redirect
  export let redirect_on_created: string | null = null

  // New project if no project is provided
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
      // only send the fields that are being updated in the UI
      let body = {
        name: project.name,
        description: project.description,
      }
      let create = !project.id
      if (!project.id /* create, but ts wants this check */) {
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
            // @ts-expect-error Patching only takes some fields
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

      // now reload the projects, which should fetch the new project as current_project
      await load_projects()
      error = null
      if (create) {
        created = true
      }
      saved = true
      // Wait for saved to propagate to warn_before_unload
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

  let import_project_path = ""

  const import_project = async () => {
    try {
      submitting = true
      saved = false
      const { data, error: post_error } = await client.POST(
        "/api/import_project",
        {
          params: {
            query: {
              project_path: import_project_path,
            },
          },
        },
      )
      if (post_error) {
        throw post_error
      }

      posthog.capture("import_project", {})

      await load_projects()
      created = true
      saved = true
      // Wait for saved to propagate to warn_before_unload
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
    {#if !importing}
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
          <button class="link font-bold" on:click={() => (importing = true)}>
            import an existing project
          </button>
        </p>
      {/if}
    {:else}
      <FormContainer
        submit_label="Import Project"
        on:submit={import_project}
        bind:warn_before_unload
        bind:submitting
        bind:error
        bind:saved
      >
        <FormElement
          label="Existing Project Path"
          description="The path to the project on your local machine. For example, /Users/username/Kiln Projects/my_project/project.kiln"
          id="import_project_path"
          inputType="input"
          bind:value={import_project_path}
        />
      </FormContainer>
      <p class="mt-4 text-center">
        Or
        <button class="link font-bold" on:click={() => (importing = false)}>
          create a new project
        </button>
      </p>
    {/if}
  {:else if !redirect_on_created}
    {#if importing}
      <h2 class="text-xl font-medium text-center">Project Imported!</h2>
      <p class="text-sm text-center">
        Your project "{import_project_path}" has been imported.
      </p>
    {:else}
      <h2 class="text-xl font-medium text-center">Project Created!</h2>
      <p class="text-sm text-center">
        Your new project "{project.name}" has been created.
      </p>
    {/if}
  {/if}
</div>

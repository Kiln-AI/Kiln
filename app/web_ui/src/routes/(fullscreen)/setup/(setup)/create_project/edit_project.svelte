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
  import { _ } from "svelte-i18n"

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
        throw new Error($_("forms.project_name_required"))
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
        submit_label={project.id
          ? $_("project.update_project")
          : $_("project.create_project")}
        on:submit={save_project}
        bind:warn_before_unload
        bind:submitting
        bind:error
        bind:saved
      >
        <FormElement
          label={$_("project.name")}
          id="project_name"
          inputType="input"
          bind:value={project.name}
          max_length={120}
        />
        <FormElement
          label={$_("project.description")}
          id="project_description"
          inputType="textarea"
          optional={true}
          bind:value={project.description}
        />
      </FormContainer>
      {#if !project.id}
        <p class="mt-4 text-center">
          {$_("common.or")}
          <button class="link font-bold" on:click={() => (importing = true)}>
            {$_("project.import_existing_project")}
          </button>
        </p>
      {/if}
    {:else}
      <FormContainer
        submit_label={$_("project.import_project")}
        on:submit={import_project}
        bind:warn_before_unload
        bind:submitting
        bind:error
        bind:saved
      >
        <FormElement
          label={$_("project.existing_project_path")}
          description={$_("project.project_path_description")}
          id="import_project_path"
          inputType="input"
          bind:value={import_project_path}
        />
      </FormContainer>
      <p class="mt-4 text-center">
        {$_("common.or")}
        <button class="link font-bold" on:click={() => (importing = false)}>
          {$_("project.create_new_project")}
        </button>
      </p>
    {/if}
  {:else if !redirect_on_created}
    {#if importing}
      <h2 class="text-xl font-medium text-center">
        {$_("project.project_imported")}
      </h2>
      <p class="text-sm text-center">
        {$_("project.project_imported_message", {
          values: { path: import_project_path },
        })}
      </p>
    {:else}
      <h2 class="text-xl font-medium text-center">
        {$_("project.project_created")}
      </h2>
      <p class="text-sm text-center">
        {$_("project.project_created_message", {
          values: { name: project.name },
        })}
      </p>
    {/if}
  {/if}
</div>

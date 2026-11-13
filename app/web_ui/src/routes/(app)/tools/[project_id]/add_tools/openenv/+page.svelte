<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Callout from "$lib/ui/callout.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import BuildingsIcon from "$lib/ui/icons/buildings_icon.svelte"
  import { client } from "$lib/api_client"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { uncache_available_tools, ui_state } from "$lib/stores"
  import {
    OPENENV_DOCS_URL,
    OPENENV_SERVER_FIELDS,
    SEAHAVEN_URL,
  } from "$lib/utils/openenv"
  import posthog from "posthog-js"
  import { agentInfo } from "$lib/agent"

  $: project_id = $page.params.project_id!
  $: agentInfo.set({
    name: "Connect OpenEnv Server",
    description: `Connect an OpenEnv server to project ID ${project_id}. Adds the tools the server serves to the project.`,
  })

  let name = ""
  let description = ""
  let url = ""
  let error: KilnError | null = null
  let submitting = false

  async function connect() {
    try {
      error = null
      const { data, error: api_error } = await client.POST(
        "/api/projects/{project_id}/openenv_servers",
        {
          params: { path: { project_id } },
          body: { name, description: description || null, url },
        },
      )
      if (api_error) {
        throw api_error
      }
      if (!data.id) {
        throw new KilnError("The new OpenEnv server has no id.")
      }
      posthog.capture("connect_openenv", {})
      uncache_available_tools(project_id)
      goto(`/tools/${project_id}/openenv_servers/${data.id}`)
    } catch (e) {
      error = createKilnError(e)
    } finally {
      submitting = false
    }
  }
</script>

<AppPage
  title="Connect OpenEnv Server"
  subtitle="Connect to a running OpenEnv server to add its tools to your project."
  sub_subtitle="Read the Docs"
  sub_subtitle_link={OPENENV_DOCS_URL}
  breadcrumbs={[
    {
      label: "Optimize",
      href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
    },
    {
      label: "Tools",
      href: `/tools/${project_id}`,
    },
    {
      label: "Add Tools",
      href: `/tools/${project_id}/add_tools`,
    },
  ]}
>
  <div class="mb-8 max-w-4xl">
    <Callout
      title="Build an OpenEnv Server with Kiln Seahaven"
      description="Kiln Seahaven is an open-source framework for building realistic copies of your product's tools and data, served as an OpenEnv server."
      button_label="Learn More"
      button_onclick={() =>
        window.open(SEAHAVEN_URL, "_blank", "noopener,noreferrer")}
    >
      <div slot="icon"><BuildingsIcon /></div>
    </Callout>
  </div>
  <div class="max-w-4xl">
    <FormContainer submit_label="Connect" on:submit={connect} bind:submitting>
      <FormElement
        label={OPENENV_SERVER_FIELDS.name.label}
        id="name"
        description={OPENENV_SERVER_FIELDS.name.description}
        bind:value={name}
        max_length={120}
      />
      <FormElement
        label={OPENENV_SERVER_FIELDS.description.label}
        inputType="textarea"
        id="openenv_server_description"
        description={OPENENV_SERVER_FIELDS.description.description}
        optional={true}
        bind:value={description}
      />
      <FormElement
        label={OPENENV_SERVER_FIELDS.url.label}
        id="openenv_server_url"
        description={OPENENV_SERVER_FIELDS.url.description}
        placeholder={OPENENV_SERVER_FIELDS.url.placeholder}
        bind:value={url}
      />

      {#if error}
        <ErrorDetailsBlock
          title="Could Not Connect to OpenEnv Server"
          error_messages={error.getErrorMessages()}
          troubleshooting_steps={[
            "Verify the URL is correct.",
            "Verify the server is running and accessible.",
            "Check your network connection.",
            "Check Kiln logs for additional details.",
          ]}
        />
      {/if}
    </FormContainer>
  </div>
</AppPage>

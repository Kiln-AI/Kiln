<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import FormElement from "$lib/utils/form_element.svelte"
  import Callout from "$lib/ui/callout.svelte"
  import ErrorDetailsBlock from "$lib/ui/error_details_block.svelte"
  import BuildingsIcon from "$lib/ui/icons/buildings_icon.svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { KilnError } from "$lib/utils/error_handlers"
  import { uncache_available_tools, ui_state } from "$lib/stores"
  import {
    OPENENV_DOCS_URL,
    OPENENV_SERVER_FIELDS,
    OPENENV_UNREACHABLE_STEPS,
    OPENENV_UNREACHABLE_TITLE,
    SEAHAVEN_URL,
    openenv_server_url_error,
  } from "$lib/utils/openenv"
  import {
    create_openenv_server,
    is_openenv_unreachable,
    openenv_server_error,
  } from "$lib/api/openenv_server_api"
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
      const data = await create_openenv_server(project_id, {
        name,
        description: description || null,
        url: url.trim(),
      })
      if (!data.id) {
        throw new KilnError("The new OpenEnv server has no id.")
      }
      posthog.capture("connect_openenv", {})
      uncache_available_tools(project_id)
      goto(`/tools/${project_id}/openenv_servers/${data.id}`)
    } catch (e) {
      error = openenv_server_error(e)
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
    <FormContainer
      submit_label="Connect"
      on:submit={connect}
      bind:submitting
      error={is_openenv_unreachable(error) ? null : error}
    >
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
        validator={openenv_server_url_error}
        bind:value={url}
      />

      {#if error && is_openenv_unreachable(error)}
        <ErrorDetailsBlock
          title={OPENENV_UNREACHABLE_TITLE}
          error_messages={error.getErrorMessages()}
          troubleshooting_steps={OPENENV_UNREACHABLE_STEPS}
        />
      {/if}
    </FormContainer>
  </div>
</AppPage>

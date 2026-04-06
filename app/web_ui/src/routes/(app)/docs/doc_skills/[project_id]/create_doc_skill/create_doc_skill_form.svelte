<script lang="ts">
  import { page } from "$app/stores"
  import { client, base_url } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import FormElement from "$lib/utils/form_element.svelte"
  import FormContainer from "$lib/utils/form_container.svelte"
  import { onMount } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import TagSelector from "../../../rag_configs/[project_id]/create_rag_config/tag_selector.svelte"
  import type { ExtractorConfig, ChunkerConfig } from "$lib/types"
  import Collapse from "$lib/ui/collapse.svelte"
  import {
    build_doc_skill_sub_configs,
    DEFAULT_CONTENT_HEADER,
    type DocSkillTemplate,
  } from "../add_doc_skill/doc_skill_templates"
  import { skill_name_validator } from "$lib/utils/input_validators"
  import posthog from "posthog-js"
  import CreateChunkerDialog from "../../../rag_configs/[project_id]/create_rag_config/create_chunker_dialog.svelte"
  import CreateExtractorDialog from "../../../rag_configs/[project_id]/create_rag_config/create_extractor_dialog.svelte"
  import {
    build_chunker_options,
    build_extractor_options,
  } from "../../../rag_configs/[project_id]/create_rag_config/options_groups"
  import PropertyList from "$lib/ui/property_list.svelte"
  import RunDocSkillDialog from "../run_doc_skill_dialog.svelte"

  $: project_id = $page.params.project_id!
  export let template: DocSkillTemplate | null = null
  export let clone_id: string | null = null
  let customize_template_mode = false

  let error: KilnError | null = null
  let skill_name: string = ""
  let name: string = ""
  let skill_content_header: string = DEFAULT_CONTENT_HEADER
  let selected_tags: string[] = []
  let strip_file_extensions: boolean = true

  let show_create_extractor_dialog: Dialog | null = null
  let show_create_chunker_dialog: Dialog | null = null

  let selected_extractor_config_id: string | null = null
  let selected_chunker_config_id: string | null = null

  let extractor_configs: ExtractorConfig[] = []
  let chunker_configs: ChunkerConfig[] = []

  let loading: boolean = false
  let loading_extractor_configs = false
  let loading_chunker_configs = false
  $: loading_subconfig_options =
    loading_extractor_configs || loading_chunker_configs

  let modal_opened: "extractor" | "chunker" | null = null

  function handle_modal_open(modal_type: "extractor" | "chunker") {
    modal_opened = modal_type
  }

  function handle_modal_close() {
    modal_opened = null
  }

  $: extractor_options = build_extractor_options(extractor_configs)
  $: chunker_options = build_chunker_options(chunker_configs)

  function on_extractor_selected(
    _selected_id: string | null,
    prev_id: string | null,
  ) {
    if (_selected_id === "create_new" && prev_id !== "create_new") {
      show_create_extractor_dialog?.show()
      handle_modal_open("extractor")
    }
  }

  function on_chunker_selected(
    _selected_id: string | null,
    prev_id: string | null,
  ) {
    if (_selected_id === "create_new" && prev_id !== "create_new") {
      show_create_chunker_dialog?.show()
      handle_modal_open("chunker")
    }
  }

  let prev_extractor_config_id: string | null = null
  let prev_chunker_config_id: string | null = null

  $: {
    on_extractor_selected(
      selected_extractor_config_id,
      prev_extractor_config_id,
    )
    prev_extractor_config_id = selected_extractor_config_id
  }

  $: {
    on_chunker_selected(selected_chunker_config_id, prev_chunker_config_id)
    prev_chunker_config_id = selected_chunker_config_id
  }

  let run_dialog: Dialog | null = null
  let created_doc_skill_id: string | null = null

  onMount(async () => {
    await Promise.all([loadExtractorConfigs(), loadChunkerConfigs()])

    if (clone_id) {
      await load_clone_source(clone_id)
    }
  })

  async function load_clone_source(id: string) {
    try {
      const response = await fetch(
        `${base_url}/api/projects/${project_id}/doc_skills/${id}`,
      )
      if (!response.ok) {
        throw new Error("Failed to load doc skill for cloning")
      }
      const doc_skill = await response.json()
      skill_name = doc_skill.skill_name || ""
      name = doc_skill.name || ""
      skill_content_header =
        doc_skill.skill_content_header || DEFAULT_CONTENT_HEADER
      selected_tags = doc_skill.document_tags || []
      strip_file_extensions = doc_skill.strip_file_extensions ?? true
      selected_extractor_config_id = doc_skill.extractor_config_id || null
      selected_chunker_config_id = doc_skill.chunker_config_id || null
    } catch (e) {
      error = createKilnError(e)
    }
  }

  async function loadExtractorConfigs() {
    try {
      loading_extractor_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/extractor_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      extractor_configs = data || []
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading_extractor_configs = false
    }
  }

  async function loadChunkerConfigs() {
    try {
      loading_chunker_configs = true
      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/chunker_configs",
        {
          params: {
            path: {
              project_id,
            },
          },
        },
      )
      if (fetch_error) {
        throw fetch_error
      }
      chunker_configs = data || []
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading_chunker_configs = false
    }
  }

  async function create_doc_skill_custom() {
    try {
      loading = true
      error = null

      if (!skill_name || !skill_name.trim()) {
        throw new Error("Please provide a skill name.")
      }

      if (!skill_content_header || !skill_content_header.trim()) {
        throw new Error("Please provide a skill description.")
      }

      if (
        !selected_extractor_config_id ||
        selected_extractor_config_id === "create_new"
      ) {
        throw new Error("Please select an extractor configuration.")
      }

      if (
        !selected_chunker_config_id ||
        selected_chunker_config_id === "create_new"
      ) {
        throw new Error("Please select a chunker configuration.")
      }

      await create_and_run_doc_skill(
        selected_extractor_config_id,
        selected_chunker_config_id,
      )
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function create_doc_skill_from_template() {
    if (!template) {
      return
    }

    try {
      loading = true
      error = null

      if (!skill_name || !skill_name.trim()) {
        throw new Error("Please provide a skill name.")
      }

      if (!skill_content_header || !skill_content_header.trim()) {
        throw new Error("Please provide a skill description.")
      }

      const { extractor_config_id, chunker_config_id } =
        await build_doc_skill_sub_configs(
          template,
          project_id,
          extractor_configs,
          chunker_configs,
        )

      await create_and_run_doc_skill(extractor_config_id, chunker_config_id)
    } catch (err) {
      error = createKilnError(err)
    } finally {
      loading = false
    }
  }

  async function create_and_run_doc_skill(
    extractor_config_id: string,
    chunker_config_id: string,
  ) {
    const response = await fetch(
      `${base_url}/api/projects/${project_id}/doc_skills`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: name || template?.doc_skill_name || skill_name,
          skill_name: skill_name,
          skill_content_header: skill_content_header,
          description: null,
          extractor_config_id: extractor_config_id,
          chunker_config_id: chunker_config_id,
          document_tags: selected_tags.length > 0 ? selected_tags : null,
          strip_file_extensions: strip_file_extensions,
        }),
      },
    )

    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(
        body?.detail || `Failed to create doc skill (${response.status})`,
      )
    }

    const doc_skill = await response.json()
    if (!doc_skill.id) {
      throw new Error("Failed to create doc skill: missing ID")
    }

    created_doc_skill_id = doc_skill.id

    posthog.capture("create_doc_skill", {
      template_name: template?.name || "custom",
      tag_filter: selected_tags.length > 0,
      strip_file_extensions: strip_file_extensions,
    })

    run_dialog?.show()
  }

  async function customize_template() {
    if (!template) {
      return
    }
    try {
      loading = true
      const { extractor_config_id, chunker_config_id } =
        await build_doc_skill_sub_configs(
          template,
          project_id,
          extractor_configs,
          chunker_configs,
        )
      await Promise.all([loadExtractorConfigs(), loadChunkerConfigs()])
      selected_extractor_config_id = extractor_config_id
      selected_chunker_config_id = chunker_config_id
      customize_template_mode = true
    } catch (err) {
      error = createKilnError("Error customizing template: " + err)
    } finally {
      loading = false
    }
  }
</script>

{#if loading || loading_subconfig_options}
  <div class="w-full min-h-[50vh] flex justify-center items-center">
    <div class="loading loading-spinner loading-lg"></div>
  </div>
{:else}
  <FormContainer
    submit_visible={true}
    submit_label="Create Doc Skill"
    on:submit={async () => {
      if (template && !customize_template_mode) {
        await create_doc_skill_from_template()
      } else {
        await create_doc_skill_custom()
      }
    }}
    {error}
    gap={4}
    bind:submitting={loading}
    keyboard_submit={!modal_opened}
  >
    <div class="text-xl font-bold">Skill Properties</div>
    <FormElement
      label="Skill Name"
      description="Kebab-case name used by agents to load this skill (e.g., company-docs)."
      inputType="input"
      id="skill_name"
      bind:value={skill_name}
      validator={skill_name_validator}
      placeholder="e.g. company-docs, api-reference"
    />
    <FormElement
      label="Config Name"
      description="A display name for this configuration."
      inputType="input"
      id="config_name"
      bind:value={name}
      placeholder="e.g. Company Docs - Medium Context"
      optional={true}
    />
    <FormElement
      label="Skill Description"
      description="Describes the documents in this skill. Placed at the top of the skill file that agents read."
      inputType="textarea"
      id="skill_content_header"
      max_length={16384}
      bind:value={skill_content_header}
    />

    <div class="flex flex-col gap-2">
      <TagSelector
        {project_id}
        bind:selected_tags
        on:change={(e) => (selected_tags = e.detail.selected_tags)}
      />
    </div>

    <div>
      <div class="text-xl font-bold mt-4">Processing Configuration</div>
      <div class="text-xs text-gray-500 font-medium">
        Controls how documents are extracted and chunked into skill parts.
      </div>
    </div>

    {#if template && !customize_template_mode}
      <div class="flex flex-col">
        <div class="mb-8">
          <PropertyList
            properties={[
              { name: "Template Name", value: template.name },
              {
                name: "Extractor Model",
                value: template.extractor.description,
                tooltip:
                  "The model used to extract text from your documents (PDFs, images, videos, etc).",
              },
              {
                name: "Chunking Strategy",
                value: template.chunker.description,
                tooltip:
                  "Parameters for splitting larger documents into smaller parts.",
              },
              ...(template.notice_text
                ? [
                    {
                      name: "Note",
                      value: template.notice_text,
                      warn_icon: true,
                      tooltip: template.notice_tooltip,
                    },
                  ]
                : []),
            ]}
          />
          <div class="flex flex-row items-center gap-2 mt-4">
            <button
              class="btn btn-sm px-6"
              on:click={() => {
                customize_template()
              }}
            >
              Customize Configuration
            </button>
            <div class="badge badge-sm badge-outline">Advanced</div>
          </div>
        </div>
      </div>
    {:else}
      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <FormElement
            id="extractor_select"
            label="Extractor"
            description="Extractors convert your documents into text."
            info_description="Documents like PDFs, images and videos need to be converted into text."
            fancy_select_options={extractor_options}
            bind:value={selected_extractor_config_id}
            inputType="fancy_select"
          />
        </div>
        <div class="flex flex-col gap-2">
          <FormElement
            id="chunker_select"
            label="Chunker"
            description="Split document text into smaller parts for the skill."
            info_description="Splitting long documents into smaller parts allows agents to load relevant sections on demand."
            fancy_select_options={chunker_options}
            bind:value={selected_chunker_config_id}
            inputType="fancy_select"
          />
        </div>
      </div>
    {/if}

    <Collapse title="Advanced Options">
      <div class="flex items-center gap-3">
        <input
          type="checkbox"
          class="toggle toggle-primary"
          bind:checked={strip_file_extensions}
          id="strip_extensions"
        />
        <label for="strip_extensions" class="text-sm">
          Remove file extensions from document names
        </label>
      </div>
    </Collapse>
  </FormContainer>
{/if}

<CreateExtractorDialog
  bind:dialog={show_create_extractor_dialog}
  keyboard_submit={modal_opened === "extractor"}
  on:success={async (e) => {
    await loadExtractorConfigs()
    selected_extractor_config_id = e.detail.extractor_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_extractor_config_id === "create_new") {
      selected_extractor_config_id = null
    }
    show_create_extractor_dialog?.close()
  }}
/>

<CreateChunkerDialog
  bind:dialog={show_create_chunker_dialog}
  keyboard_submit={modal_opened === "chunker"}
  on:success={async (e) => {
    await loadChunkerConfigs()
    selected_chunker_config_id = e.detail.chunker_config_id
  }}
  on:close={() => {
    handle_modal_close()
    if (selected_chunker_config_id === "create_new") {
      selected_chunker_config_id = null
    }
    show_create_chunker_dialog?.close()
  }}
/>

{#if created_doc_skill_id}
  <RunDocSkillDialog
    bind:dialog={run_dialog}
    {project_id}
    doc_skill_id={created_doc_skill_id}
  />
{/if}

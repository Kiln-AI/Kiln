<script lang="ts">
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import { client } from "$lib/api_client"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import AppPage from "../../../../../app_page.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { goto } from "$app/navigation"
  import { onMount } from "svelte"
  import { extractor_output_format, formatDate } from "$lib/utils/formatters"
  import {
    load_available_models,
    model_name,
    provider_name_from_id,
  } from "$lib/stores"
  import type { ExtractorConfig, ChunkerConfig } from "$lib/types"
  import Warning from "$lib/ui/warning.svelte"
  import posthog from "posthog-js"
  import Dialog from "$lib/ui/dialog.svelte"
  import RunDocSkillDialog from "../../run_doc_skill_dialog.svelte"
  import { agentInfo } from "$lib/agent"
  import { fixedWindowChunkerProperties } from "$lib/utils/properties_cast"
  import type { components } from "$lib/api_schema"

  type DocSkillResponse = components["schemas"]["DocSkillResponse"]

  $: project_id = $page.params.project_id!
  $: doc_skill_id = $page.params.doc_skill_id!
  $: agentInfo.set({
    name: "Doc Skill Detail",
    description: `Doc Skill configuration detail for ID ${doc_skill_id} in project ID ${project_id}.`,
  })

  let loading = true
  let error: KilnError | null = null
  let update_error: KilnError | null = null
  let doc_skill: DocSkillResponse | null = null
  let extractor_config: ExtractorConfig | null = null
  let chunker_config: ChunkerConfig | null = null

  let run_dialog: Dialog | null = null

  onMount(async () => {
    await Promise.all([load_available_models(), load_doc_skill()])
  })

  async function load_doc_skill() {
    try {
      loading = true
      error = null

      const { data, error: fetch_error } = await client.GET(
        "/api/projects/{project_id}/doc_skills/{doc_skill_id}",
        {
          params: { path: { project_id, doc_skill_id } },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      doc_skill = data || null

      await load_sub_configs()
    } catch (e) {
      error = createKilnError(e)
    } finally {
      loading = false
    }
  }

  async function load_sub_configs() {
    if (!doc_skill) return

    const [extractor_result, chunker_result] = await Promise.all([
      client.GET(
        "/api/projects/{project_id}/extractor_configs/{extractor_config_id}",
        {
          params: {
            path: {
              project_id,
              extractor_config_id: doc_skill.extractor_config_id,
            },
          },
        },
      ),
      client.GET("/api/projects/{project_id}/chunker_configs", {
        params: {
          path: {
            project_id,
          },
        },
      }),
    ])

    if (extractor_result.data) {
      extractor_config = extractor_result.data
    }
    if (chunker_result.data) {
      chunker_config =
        chunker_result.data.find(
          (c) => c.id === doc_skill?.chunker_config_id,
        ) ?? null
    }
  }

  async function update_archived_state(is_archived: boolean) {
    try {
      update_error = null

      const { error: fetch_error } = await client.PATCH(
        "/api/projects/{project_id}/doc_skills/{doc_skill_id}",
        {
          params: { path: { project_id, doc_skill_id } },
          body: { is_archived },
        },
      )

      if (fetch_error) {
        throw fetch_error
      }

      await load_doc_skill()

      posthog.capture(
        is_archived ? "archive_doc_skill" : "unarchive_doc_skill",
        {},
      )
    } catch (e) {
      update_error = createKilnError(e)
    }
  }

  $: sorted_tags = doc_skill?.document_tags
    ? doc_skill.document_tags.toSorted()
    : null

  $: fixed_window_properties =
    chunker_config?.chunker_type === "fixed_window"
      ? fixedWindowChunkerProperties(chunker_config)
      : null
</script>

<div class="max-w-[1400px]">
  <AppPage
    title="Documents Skill"
    subtitle={doc_skill?.name ? `Name: ${doc_skill.name}` : undefined}
    breadcrumbs={[
      {
        label: "Optimize",
        href: `/optimize/${project_id}/${$ui_state.current_task_id}`,
      },
      {
        label: "Docs & Search",
        href: `/docs/${project_id}`,
      },
      {
        label: "Doc Skills",
        href: `/docs/doc_skills/${project_id}`,
      },
    ]}
    action_buttons={doc_skill && !loading && !error
      ? [
          {
            label: "Clone",
            handler: () =>
              goto(
                `/docs/doc_skills/${project_id}/create_doc_skill?clone=${doc_skill_id}`,
              ),
          },
          {
            label: doc_skill.is_archived ? "Unarchive" : "Archive",
            primary: doc_skill.is_archived,
            handler: () => {
              if (!doc_skill) return
              update_archived_state(!doc_skill.is_archived)
            },
          },
        ]
      : []}
  >
    {#if loading}
      <div class="w-full min-h-[50vh] flex justify-center items-center">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if error}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">
          {error.getMessage() || "An unknown error occurred"}
        </div>
      </div>
    {:else if !doc_skill}
      <div
        class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
      >
        <div class="text-error text-sm">Doc Skill not found</div>
      </div>
    {:else}
      {#if update_error}
        <div class="my-4 text-error">
          <span>{update_error.getMessage() || "Update failed"}</span>
        </div>
      {/if}
      {#if doc_skill.is_archived}
        <Warning
          warning_message="This Doc Skill is archived. You may unarchive it to use it again."
          large_icon={true}
          warning_color="warning"
          outline={true}
        />
      {/if}
      <div class="flex flex-col lg:flex-row gap-8 xl:gap-12">
        <!-- Left Column - Configuration & Actions -->
        <div class="flex-1 flex flex-col gap-6">
          {#if !doc_skill.skill_id && !doc_skill.is_archived}
            <div
              class="rounded-lg border border-warning bg-warning/10 p-4 flex flex-col gap-2"
            >
              <div class="font-bold">Incomplete</div>
              <div class="text-sm">
                This doc skill has not been built yet. Run the pipeline to
                extract, chunk, and create the skill.
              </div>
              <button
                class="btn btn-warning btn-sm mt-1 self-start"
                on:click={() => run_dialog?.show()}
              >
                Run Pipeline
              </button>
            </div>
          {:else if !doc_skill.skill_id && doc_skill.is_archived}
            <div
              class="rounded-lg border border-warning bg-warning/10 p-4 flex flex-col gap-2"
            >
              <div class="font-bold">Incomplete</div>
              <div class="text-sm">
                This doc skill was archived before the pipeline completed.
                Unarchive to run the pipeline.
              </div>
            </div>
          {/if}

          <PropertyList
            title="Configuration"
            properties={[
              { name: "Name", value: doc_skill.name },
              {
                name: "Skill Name",
                value: doc_skill.skill_name,
                ...(doc_skill.skill_id
                  ? {
                      link: `/skills/${project_id}/${doc_skill.skill_id}`,
                    }
                  : {}),
              },
              ...(doc_skill.description
                ? [
                    {
                      name: "Description",
                      value: doc_skill.description,
                    },
                  ]
                : []),
              {
                name: "Created At",
                value: formatDate(doc_skill.created_at ?? undefined),
              },
              ...(doc_skill.created_by
                ? [{ name: "Created By", value: doc_skill.created_by }]
                : []),
            ]}
          />

          {#if doc_skill.skill_id}
            <a
              href={`/skills/${project_id}/${doc_skill.skill_id}`}
              class="btn btn-primary btn-sm btn-wide self-start"
            >
              View Skill
            </a>
          {/if}
        </div>

        <!-- Right Sidebar - Pipeline Details -->
        <div class="w-full lg:w-80 xl:w-96 flex-shrink-0">
          <div class="flex flex-col gap-6">
            <PropertyList
              title="Extractor"
              properties={extractor_config
                ? [
                    {
                      name: "Model Provider",
                      value:
                        provider_name_from_id(
                          extractor_config.model_provider_name,
                        ) || "N/A",
                    },
                    {
                      name: "Model",
                      value:
                        model_name(extractor_config.model_name, null) || "N/A",
                    },
                    {
                      name: "Output Format",
                      value: extractor_output_format(
                        extractor_config.output_format,
                      ),
                    },
                    {
                      name: "Configuration",
                      value: "View Extractor",
                      link: `/docs/extractors/${project_id}/${extractor_config.id}/extractor`,
                    },
                  ]
                : [
                    {
                      name: "Extractor",
                      value: "Configuration not found",
                      error: true,
                    },
                  ]}
            />

            {#if chunker_config}
              <PropertyList
                title="Chunker"
                properties={[
                  {
                    name: "Type",
                    value:
                      chunker_config.chunker_type === "fixed_window"
                        ? "Fixed Window"
                        : chunker_config.chunker_type === "semantic"
                          ? "Semantic"
                          : chunker_config.chunker_type,
                  },
                  ...(fixed_window_properties
                    ? [
                        {
                          name: "Chunk Size",
                          value: `${fixed_window_properties.chunk_size ?? "N/A"} tokens`,
                        },
                        {
                          name: "Overlap",
                          value: `${fixed_window_properties.chunk_overlap ?? "N/A"} tokens`,
                        },
                      ]
                    : []),
                ]}
              />
            {:else}
              <PropertyList
                title="Chunker"
                properties={[
                  {
                    name: "Chunker",
                    value: "Configuration not found",
                    error: true,
                  },
                ]}
              />
            {/if}

            <div>
              <div class="text-xl font-bold mb-1">Documents</div>
              <div class="flex flex-row flex-wrap gap-2 text-sm items-center">
                {#if sorted_tags && sorted_tags.length > 0}
                  Documents with the {sorted_tags.length === 1 ? "tag" : "tags"}
                  {#each sorted_tags as tag}
                    <div
                      class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full"
                    >
                      <span class="truncate">{tag}</span>
                    </div>
                  {/each}
                {:else}
                  All documents in library.
                {/if}
              </div>
            </div>
          </div>
        </div>
      </div>
    {/if}
  </AppPage>
</div>

{#if doc_skill && !doc_skill.skill_id}
  <RunDocSkillDialog
    bind:dialog={run_dialog}
    {project_id}
    doc_skill_id={doc_skill.id}
  />
{/if}

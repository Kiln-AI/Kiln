<script lang="ts">
  import AppPage from "../../../../app_page.svelte"
  import { page } from "$app/stores"
  import { onMount } from "svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import type { Spec, SpecStatus } from "$lib/types"
  import { client } from "$lib/api_client"
  import TagPicker from "$lib/ui/tag_picker.svelte"
  import { formatSpecType } from "$lib/utils/formatters"
  import EditableSpecField from "../editable_spec_field.svelte"
  import type { OptionGroup } from "$lib/ui/fancy_select_types"

  // ### Spec Details Page ###

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id
  $: spec_id = $page.params.spec_id

  let spec: Spec | null = null
  let spec_error: KilnError | null = null
  let spec_loading = true
  let tags_error: KilnError | null = null
  let current_tags: string[] = []
  let updating_priorities = false
  let updating_statuses = false
  let priorityField: EditableSpecField | null = null
  let statusField: EditableSpecField | null = null

  $: if (spec) {
    current_tags = spec.tags || []
  }

  function getPriorityOptions(): OptionGroup[] {
    return [
      {
        options: [
          { label: "P0", value: 0 },
          { label: "P1", value: 1 },
          { label: "P2", value: 2 },
          { label: "P3", value: 3 },
        ],
      },
    ]
  }

  function getStatusOptions(): OptionGroup[] {
    return [
      {
        options: [
          { label: "Active", value: "active" },
          { label: "Future", value: "future" },
          { label: "Deprecated", value: "deprecated" },
          { label: "Archived", value: "archived" },
        ],
      },
    ]
  }

  async function updateSpecPriority(newPriority: number) {
    if (!spec?.id || spec.priority === newPriority || updating_priorities) {
      return
    }

    updating_priorities = true
    try {
      const { data, error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id: spec.id },
          },
          body: {
            name: spec.name,
            definition: spec.definition,
            properties: spec.properties,
            priority: newPriority as 0 | 1 | 2 | 3,
            status: spec.status,
            tags: spec.tags,
            eval_id: spec.eval_id ?? null,
          },
        },
      )

      if (error) {
        throw error
      }

      spec = data
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      updating_priorities = false
    }
  }

  async function updateSpecStatus(newStatus: SpecStatus) {
    if (!spec?.id || spec.status === newStatus || updating_statuses) {
      return
    }

    updating_statuses = true
    try {
      const { data, error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id: spec.id },
          },
          body: {
            name: spec.name,
            definition: spec.definition,
            properties: spec.properties,
            priority: spec.priority,
            status: newStatus,
            tags: spec.tags,
            eval_id: spec.eval_id ?? null,
          },
        },
      )

      if (error) {
        throw error
      }

      spec = data
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      updating_statuses = false
    }
  }

  function handlePriorityUpdate(spec: Spec, value: number | SpecStatus) {
    updateSpecPriority(value as number)
  }

  function handleStatusUpdate(spec: Spec, value: number | SpecStatus) {
    updateSpecStatus(value as SpecStatus)
  }

  onMount(async () => {
    await load_spec()
  })

  async function load_spec() {
    try {
      spec_loading = true
      spec_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id },
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
      current_tags = spec.tags || []
    } catch (error) {
      spec_error = createKilnError(error)
    } finally {
      spec_loading = false
    }
  }

  async function save_tags(tags: string[]) {
    try {
      if (!spec?.id) return
      tags_error = null
      const { data, error } = await client.PATCH(
        "/api/projects/{project_id}/tasks/{task_id}/specs/{spec_id}",
        {
          params: {
            path: { project_id, task_id, spec_id: spec.id },
          },
          body: {
            name: spec.name,
            definition: spec.definition,
            properties: spec.properties,
            priority: spec.priority,
            status: spec.status,
            tags: tags,
            eval_id: spec.eval_id || null,
          },
        },
      )
      if (error) {
        throw error
      }
      spec = data
      current_tags = spec.tags || []
    } catch (err) {
      tags_error = createKilnError(err)
    }
  }
</script>

<AppPage
  title={`Spec: ${spec?.name ? `${spec.name}` : ""}`}
  breadcrumbs={[
    {
      label: "Specs",
      href: `/specs/${project_id}/${task_id}`,
    },
  ]}
>
  {#if spec_loading}
    <div class="flex justify-center items-center h-full">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if spec_error}
    <div class="text-error text-sm">
      {spec_error.getMessage() || "An unknown error occurred"}
    </div>
  {:else if !spec}
    <div class="text-error text-sm">
      Failed to load spec, please refresh the page and try again.
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-[900px,500px] gap-12">
      <div class="grow">
        <div class="text-xl font-bold mb-4">Definition</div>
        <div class="bg-base-200 rounded-lg p-6">
          <div class="prose prose-sm max-w-none whitespace-pre-wrap">
            {spec.definition}
          </div>
        </div>
      </div>
      <div class="flex flex-col gap-4">
        <div>
          <div class="text-xl font-bold mb-4">Properties</div>
          <div
            class="grid grid-cols-[auto,1fr] gap-y-2 gap-x-4 text-sm 2xl:text-base"
          >
            <div class="flex items-center">ID</div>
            <div class="flex items-center overflow-x-hidden text-gray-500 px-2">
              {spec.id ?? "None"}
            </div>
            <div class="flex items-center">Type</div>
            <div class="flex items-center overflow-x-hidden text-gray-500 px-2">
              {formatSpecType(spec.properties.spec_type)}
            </div>
            <div class="flex items-center">Priority</div>
            <div class="flex items-center overflow-x-hidden text-gray-500 px-1">
              <EditableSpecField
                bind:this={priorityField}
                {spec}
                field="priority"
                options={getPriorityOptions()}
                aria_label="Priority"
                onUpdate={handlePriorityUpdate}
                compact={true}
                onOpen={() => {
                  statusField?.close()
                }}
              />
            </div>
            <div class="flex items-center">Status</div>
            <div class="flex items-center overflow-x-hidden text-gray-500 px-1">
              <EditableSpecField
                bind:this={statusField}
                {spec}
                field="status"
                options={getStatusOptions()}
                aria_label="Status"
                onUpdate={handleStatusUpdate}
                compact={true}
                onOpen={() => {
                  priorityField?.close()
                }}
              />
            </div>
            <div class="flex items-center">Eval ID</div>
            <div class="flex items-center overflow-x-hidden text-gray-500 px-2">
              {spec.eval_id || "None"}
            </div>
          </div>
        </div>
        <div class="text-xl font-bold mt-8">Tags</div>
        {#if tags_error}
          <div class="text-error text-sm mb-2">
            {tags_error.getMessage() || "An unknown error occurred"}
          </div>
        {/if}
        <TagPicker
          tags={current_tags}
          tag_type="task_run"
          {project_id}
          {task_id}
          on:tags_changed={(event) => {
            save_tags(event.detail.current)
          }}
        />
      </div>
    </div>
  {/if}
</AppPage>

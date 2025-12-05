<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import { page } from "$app/stores"
  import { createKilnError, KilnError } from "$lib/utils/error_handlers"
  import { client } from "$lib/api_client"
  import { onMount } from "svelte"
  import Intro from "$lib/ui/intro.svelte"
  import type { Spec, SpecStatus } from "$lib/types"
  import { goto, replaceState } from "$app/navigation"
  import Dialog from "$lib/ui/dialog.svelte"
  import FilterTagsDialog from "$lib/ui/filter_tags_dialog.svelte"
  import TableToolbar from "$lib/ui/table_toolbar.svelte"
  import AddTagsDialog from "$lib/ui/add_tags_dialog.svelte"
  import RemoveTagsDialog from "$lib/ui/remove_tags_dialog.svelte"
  import {
    capitalize,
    formatDate,
    formatPriority,
    formatSpecType,
  } from "$lib/utils/formatters"

  // ### Spec Table ###

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let specs: Spec[] | null = null
  let specs_error: KilnError | null = null
  let specs_loading = true
  let sortColumn: "name" | "template" | "priority" | "status" | "created_at" =
    "created_at"
  let sortDirection: "asc" | "desc" = "desc"
  let filter_tags = ($page.url.searchParams.getAll("tags") || []) as string[]
  let filtered_specs: Spec[] | null = null
  let sorted_specs: Spec[] | null = null
  let tags_dialog: Dialog | null = null
  let selected_spec_tags: string[] = []
  let filter_tags_dialog: FilterTagsDialog | null = null

  let select_mode: boolean = false
  let selected_specs: Set<string> = new Set()
  let select_summary: "all" | "none" | "some" = "none"
  $: {
    if (selected_specs.size >= (filtered_specs?.length || 0)) {
      select_summary = "all"
    } else if (selected_specs.size > 0) {
      select_summary = "some"
    } else {
      select_summary = "none"
    }
  }

  $: archive_action_state = (() => {
    if (selected_specs.size === 0) return null
    const selected_spec_objects = (filtered_specs || []).filter(
      (spec) => spec.id && selected_specs.has(spec.id),
    )
    if (selected_spec_objects.length === 0) return null

    const all_archived = selected_spec_objects.every(
      (spec) => spec.status === "archived",
    )
    const all_unarchived = selected_spec_objects.every(
      (spec) => spec.status !== "archived",
    )

    if (all_archived) return "unarchive"
    if (all_unarchived) return "archive"
    return "mixed"
  })()

  let add_tags: string[] = []
  let remove_tags: Set<string> = new Set()
  let add_tags_dialog: AddTagsDialog | null = null
  let remove_tags_dialog: RemoveTagsDialog | null = null
  let removeable_tags: Record<string, number> = {}
  let show_archived = false

  type SortableColumn =
    | "name"
    | "template"
    | "priority"
    | "status"
    | "created_at"
  type TableColumn = {
    key: string
    label: string
    sortable: boolean
    sortKey?: SortableColumn
  }
  const tableColumns: TableColumn[] = [
    { key: "name", label: "Name", sortable: true, sortKey: "name" },
    { key: "definition", label: "Definition", sortable: false },
    { key: "template", label: "Template", sortable: true, sortKey: "template" },
    { key: "priority", label: "Priority", sortable: true, sortKey: "priority" },
    { key: "status", label: "Status", sortable: true, sortKey: "status" },
    { key: "tags", label: "Tags", sortable: false },
    {
      key: "created_at",
      label: "Created At",
      sortable: true,
      sortKey: "created_at",
    },
  ]

  $: {
    const url = new URL(window.location.href)
    filter_tags = url.searchParams.getAll("tags") as string[]
    filterAndSortSpecs()
  }

  $: is_empty = !specs || specs.length === 0
  $: has_archived_specs = specs
    ? specs.some((spec) => spec.status === "archived")
    : false

  onMount(async () => {
    await load_specs()
  })

  async function load_specs() {
    try {
      specs_loading = true
      specs_error = null
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/specs",
        {
          params: {
            path: { project_id, task_id },
          },
        },
      )
      if (error) {
        throw error
      }
      specs = data
      if (specs && specs.length > 0) {
        const all_archived = specs.every((spec) => spec.status === "archived")
        if (all_archived) {
          show_archived = true
        }
      }
      filterAndSortSpecs()
    } catch (error) {
      specs_error = createKilnError(error)
    } finally {
      specs_loading = false
    }
  }

  function filterAndSortSpecs() {
    if (!specs) {
      filtered_specs = null
      sorted_specs = null
      return
    }

    let active_specs = specs.filter((spec) => spec.status !== "archived")
    let archived_specs = specs.filter((spec) => spec.status === "archived")

    let filtered_active =
      filter_tags.length > 0
        ? active_specs.filter((spec) =>
            filter_tags.every((tag) => spec.tags?.includes(tag)),
          )
        : active_specs

    let filtered_archived =
      filter_tags.length > 0
        ? archived_specs.filter((spec) =>
            filter_tags.every((tag) => spec.tags?.includes(tag)),
          )
        : archived_specs

    let all_specs_to_show = show_archived
      ? [...filtered_active, ...filtered_archived]
      : filtered_active

    if (sortColumn && sortDirection) {
      sorted_specs = [...all_specs_to_show].sort(sortFunction)
    } else {
      sorted_specs = all_specs_to_show
    }

    filtered_specs = all_specs_to_show
  }

  function getStatusSortOrder(status: SpecStatus): number {
    switch (status) {
      case "active":
        return 0
      case "future":
        return 1
      case "deprecated":
        return 2
      case "archived":
        return 3
      default: {
        const _: never = status
        return 4
      }
    }
  }

  function sortFunction(a: Spec, b: Spec) {
    let aValue: string | number | Date | null | undefined
    let bValue: string | number | Date | null | undefined

    switch (sortColumn) {
      case "name":
        aValue = a.name.toLowerCase()
        bValue = b.name.toLowerCase()
        break
      case "template":
        aValue = a.properties.spec_type
        bValue = b.properties.spec_type
        break
      case "priority":
        aValue = a.priority
        bValue = b.priority
        break
      case "status":
        aValue = getStatusSortOrder(a.status)
        bValue = getStatusSortOrder(b.status)
        break
      case "created_at":
        aValue = a.created_at ? new Date(a.created_at).getTime() : 0
        bValue = b.created_at ? new Date(b.created_at).getTime() : 0
        break
      default:
        return 0
    }

    if (!aValue && aValue !== 0) return sortDirection === "asc" ? 1 : -1
    if (!bValue && bValue !== 0) return sortDirection === "asc" ? -1 : 1

    if (aValue < bValue) return sortDirection === "asc" ? -1 : 1
    if (aValue > bValue) return sortDirection === "asc" ? 1 : -1
    return 0
  }

  function handleSort(column: SortableColumn) {
    let newDirection: "asc" | "desc" = "desc"
    if (sortColumn === column) {
      newDirection = sortDirection === "asc" ? "desc" : "asc"
    }
    sortColumn = column
    sortDirection = newDirection
    filterAndSortSpecs()
  }

  function handleColumnClick(sortKey?: string) {
    if (sortKey) {
      handleSort(sortKey as SortableColumn)
    }
  }

  function remove_filter_tag(tag: string) {
    const newTags = filter_tags.filter((t) => t !== tag)
    updateURL({ tags: newTags })
  }

  function add_filter_tag(tag: string) {
    const newTags = [...new Set([...filter_tags, tag])]
    updateURL({ tags: newTags })
  }

  function updateURL(params: Record<string, string | string[]>) {
    const url = new URL(window.location.href)

    if (params.tags) {
      url.searchParams.delete("tags")
    }

    Object.entries(params).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach((v) => url.searchParams.append(key, v))
      } else {
        url.searchParams.set(key, value.toString())
      }
    })

    if (params.tags) {
      filter_tags = params.tags as string[]
    }

    replaceState(url, {})
    filterAndSortSpecs()
  }

  $: available_filter_tags = get_available_filter_tags(
    filtered_specs,
    filter_tags,
  )

  function get_available_filter_tags(
    filtered_specs: Spec[] | null,
    filter_tags: string[],
  ): Record<string, number> {
    if (!filtered_specs) return {}

    const remaining_tags: Record<string, number> = {}
    filtered_specs.forEach((spec) => {
      spec.tags?.forEach((tag) => {
        if (filter_tags.includes(tag)) return
        if (typeof tag === "string") {
          remaining_tags[tag] = (remaining_tags[tag] || 0) + 1
        }
      })
    })
    return remaining_tags
  }

  function formatTagsDisplay(tags: string[]): {
    firstTag: string
    othersCount: number
  } {
    if (tags.length === 0) {
      return { firstTag: "", othersCount: 0 }
    }
    const sortedTags = [...tags].sort()
    return {
      firstTag: sortedTags[0],
      othersCount: sortedTags.length - 1,
    }
  }

  function showTagsDialog(tags: string[], event: Event) {
    event.stopPropagation()
    selected_spec_tags = [...tags].sort()
    tags_dialog?.show()
  }

  function toggle_selection(spec_id: string): boolean {
    const was_selected = selected_specs.has(spec_id)
    if (was_selected) {
      selected_specs.delete(spec_id)
    } else {
      selected_specs.add(spec_id)
    }
    selected_specs = selected_specs
    return !was_selected
  }

  function select_all_clicked(event: Event) {
    event.preventDefault()
    if (select_summary === "all" || select_summary === "some") {
      selected_specs.clear()
    } else {
      filtered_specs?.forEach((spec) => {
        if (spec.id) {
          selected_specs.add(spec.id)
        }
      })
    }
    selected_specs = selected_specs
  }

  function show_add_tags_modal() {
    add_tags_dialog?.show()
  }

  function show_remove_tags_modal() {
    remove_tags = new Set()
    update_removeable_tags()
    remove_tags_dialog?.show()
  }

  function update_removeable_tags() {
    let selected_spec_contents: Spec[] = []
    for (const spec of filtered_specs || []) {
      if (spec.id && selected_specs.has(spec.id)) {
        selected_spec_contents.push(spec)
      }
    }
    removeable_tags = get_available_filter_tags(
      selected_spec_contents,
      Array.from(remove_tags),
    )
  }

  async function add_selected_tags(): Promise<boolean> {
    remove_tags = new Set()
    return await edit_tags()
  }

  async function remove_selected_tags(): Promise<boolean> {
    add_tags = []
    return await edit_tags()
  }

  async function edit_tags(): Promise<boolean> {
    let success = false
    try {
      const spec_ids = Array.from(selected_specs)
      const specs_to_update = (filtered_specs || []).filter(
        (spec) => spec.id && spec_ids.includes(spec.id),
      )

      for (const spec of specs_to_update) {
        if (!spec.id) continue

        const current_tags = spec.tags || []
        let updated_tags = [...current_tags]

        if (remove_tags.size > 0) {
          updated_tags = updated_tags.filter((tag) => !remove_tags.has(tag))
        }

        if (add_tags.length > 0) {
          updated_tags = [...new Set([...updated_tags, ...add_tags])]
        }

        const { error } = await client.PATCH(
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
              tags: updated_tags,
              eval_id: spec.eval_id ?? null,
            },
          },
        )

        if (error) {
          throw error
        }
      }

      add_tags = []
      success = true
      return true
    } finally {
      // Only clear selection and reload if operation succeeded
      // If error occurred, Dialog will stay open and show error, keeping selection for retry
      if (success) {
        selected_specs = new Set()
        add_tags = []
        select_mode = false
        await load_specs()
      }
    }
  }

  function handle_tags_changed(tags: string[]) {
    add_tags = tags
  }

  function handle_remove_tag(tag: string) {
    remove_tags.delete(tag)
    remove_tags = remove_tags
    update_removeable_tags()
  }

  function handle_add_tag_to_remove(tag: string) {
    remove_tags.add(tag)
    remove_tags = remove_tags
    update_removeable_tags()
  }

  function show_archive_modal() {
    archive_dialog?.show()
  }

  async function archive_selected_specs(): Promise<boolean> {
    let success = false
    try {
      const spec_ids = Array.from(selected_specs)
      const specs_to_update = (filtered_specs || []).filter(
        (spec) => spec.id && spec_ids.includes(spec.id),
      )

      const should_archive = archive_action_state === "archive"
      const should_unarchive = archive_action_state === "unarchive"

      if (!should_archive && !should_unarchive) {
        return false
      }

      for (const spec of specs_to_update) {
        if (!spec.id) continue

        const new_status = should_archive ? "archived" : "active"

        const { error } = await client.PATCH(
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
              status: new_status,
              tags: spec.tags,
              eval_id: spec.eval_id ?? null,
            },
          },
        )

        if (error) {
          throw error
        }
      }

      success = true
      return true
    } finally {
      if (success) {
        selected_specs = new Set()
        select_mode = false
        await load_specs()
      }
    }
  }

  let archive_dialog: Dialog | null = null
</script>

<AppPage
  limit_max_width={true}
  title="Specs"
  subtitle="Define the specs your task should follow and be judged against"
  sub_subtitle={is_empty ? undefined : "Read the Docs"}
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "New Spec",
          href: `/specs/${project_id}/${task_id}/select_template`,
          primary: true,
        },
      ]}
>
  <div class="flex flex-col gap-4">
    {#if specs_loading}
      <div class="flex justify-center items-center h-full">
        <div class="loading loading-spinner loading-lg"></div>
      </div>
    {:else if specs_error}
      <div class="text-error text-sm">
        {specs_error.getMessage() || "An unknown error occurred"}
      </div>
    {:else if is_empty}
      <div class="max-w-[300px] mx-auto flex flex-col gap-2 mt-[10vh]">
        <Intro
          title="Specs"
          description_paragraphs={[
            "Specs are used to define how you want your task to behave.",
          ]}
          action_buttons={[
            {
              label: "Define a Spec",
              href: `/specs/${project_id}/${task_id}/select_template`,
              is_primary: true,
            },
          ]}
        />
      </div>
    {:else if sorted_specs}
      <a
        href={`/specs/${project_id}/${task_id}/compare`}
        class="group block mb-4"
      >
        <div class="card border p-3 rounded-md hover:bg-gray-50">
          <div class="flex flex-row gap-4 items-center">
            <div class="rounded-lg bg-blue-50 p-4">
              <svg
                class="h-12 aspect-760/621"
                viewBox="0 0 760 621"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <g clip-path="url(#clip0_1603_4)">
                  <rect
                    x="10"
                    y="10"
                    width="740"
                    height="601"
                    rx="25"
                    fill="white"
                    stroke="#628BD9"
                    stroke-width="20"
                  />
                  <line
                    x1="137"
                    y1="90.9778"
                    x2="137.999"
                    y2="541.978"
                    stroke="#628BD9"
                    stroke-width="20"
                  />
                  <line
                    x1="656"
                    y1="490"
                    x2="82"
                    y2="490"
                    stroke="#628BD9"
                    stroke-width="20"
                  />
                  <circle cx="352" cy="241" r="28" fill="#628BD9" />
                  <circle cx="473" cy="317" r="28" fill="#628BD9" />
                  <circle cx="564" cy="153" r="28" fill="#628BD9" />
                  <circle cx="232" cy="384" r="28" fill="#628BD9" />
                </g>
                <defs>
                  <clipPath id="clip0_1603_4">
                    <rect width="760" height="621" fill="white" />
                  </clipPath>
                </defs>
              </svg>
            </div>

            <div class="flex-grow flex flex-col text-sm justify-center">
              <span class="font-medium text-base"
                >Compare Models, Prompts, Tools and Fine-Tunes</span
              >
              <span class="text-sm font-light mt-1"
                >Find the best way to run this task by comparing models,
                prompts, tools and fine-tunes using evals, cost and performance.</span
              >
              <button
                class="btn btn-xs btn-outline w-fit px-6 mt-2 group-hover:bg-secondary group-hover:text-secondary-content"
                >Compare Run Configurations</button
              >
            </div>
          </div>
        </div>
      </a>

      <div class="mb-4">
        <div class="-mb-4">
          <TableToolbar
            bind:select_mode
            selected_count={selected_specs.size}
            filter_tags_count={filter_tags.length}
            onToggleSelectMode={() => (select_mode = true)}
            onCancelSelection={() => {
              select_mode = false
              selected_specs = new Set()
            }}
            onShowFilterDialog={() => filter_tags_dialog?.show()}
            onShowArchived={has_archived_specs
              ? () => {
                  show_archived = !show_archived
                  filterAndSortSpecs()
                }
              : undefined}
            {show_archived}
            onShowAddTags={show_add_tags_modal}
            onShowRemoveTags={show_remove_tags_modal}
            onShowDelete={archive_action_state === "archive" ||
            archive_action_state === "unarchive"
              ? show_archive_modal
              : undefined}
            action_type="archive"
          />
        </div>
        <div class="overflow-x-auto rounded-lg border">
          <table class="table">
            <thead>
              <tr>
                {#if select_mode}
                  <th>
                    {#key select_summary}
                      <input
                        type="checkbox"
                        class="checkbox checkbox-sm mt-1"
                        checked={select_summary === "all"}
                        indeterminate={select_summary === "some"}
                        on:change={(e) => select_all_clicked(e)}
                      />
                    {/key}
                  </th>
                {/if}
                {#each tableColumns as column}
                  {#if column.sortable && column.sortKey}
                    <th
                      on:click={() => handleColumnClick(column.sortKey)}
                      class="hover:bg-base-200 cursor-pointer"
                    >
                      {column.label}
                      <span class="inline-block w-3 text-center">
                        {sortColumn === column.sortKey
                          ? sortDirection === "asc"
                            ? "▲"
                            : "▼"
                          : "\u200B"}
                      </span>
                    </th>
                  {:else}
                    <th>
                      {column.label}
                    </th>
                  {/if}
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each sorted_specs || [] as spec}
                <tr
                  class="{select_mode
                    ? ''
                    : 'hover'} cursor-pointer {select_mode &&
                  spec.id &&
                  selected_specs.has(spec.id)
                    ? 'bg-base-200'
                    : ''} {spec.status === 'archived' ? 'opacity-60' : ''}"
                  on:click={() => {
                    if (select_mode) {
                      toggle_selection(spec.id || "")
                    } else {
                      goto(`/specs/${project_id}/${task_id}/${spec.id}`)
                    }
                  }}
                >
                  {#if select_mode}
                    <td>
                      <input
                        type="checkbox"
                        class="checkbox checkbox-sm"
                        checked={(spec.id && selected_specs.has(spec.id)) ||
                          false}
                      />
                    </td>
                  {/if}
                  <td class="font-medium">{spec.name}</td>
                  <td class="max-w-md truncate">{spec.definition}</td>
                  <td>
                    {formatSpecType(spec.properties.spec_type)}
                  </td>
                  <td>{formatPriority(spec.priority)}</td>
                  <td>
                    {capitalize(spec.status)}
                  </td>
                  <td>
                    {#if spec.tags && spec.tags.length > 0}
                      {@const tagDisplay = formatTagsDisplay(spec.tags)}
                      <div
                        class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full cursor-pointer hover:bg-gray-300"
                        on:click={(e) => showTagsDialog(spec.tags, e)}
                        role="button"
                        tabindex="0"
                        on:keydown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            showTagsDialog(spec.tags, e)
                          }
                        }}
                      >
                        <span class="truncate">{tagDisplay.firstTag}</span>
                        {#if tagDisplay.othersCount > 0}
                          <span class="ml-1 font-medium">
                            +{tagDisplay.othersCount}
                            {tagDisplay.othersCount === 1 ? "other" : "others"}
                          </span>
                        {/if}
                      </div>
                    {:else}
                      <span class="text-gray-500">None</span>
                    {/if}
                  </td>
                  <td class="text-sm text-gray-500">
                    {formatDate(spec.created_at)}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  </div>
</AppPage>

<Dialog
  bind:this={tags_dialog}
  title="Tags"
  action_buttons={[
    {
      label: "Close",
      isCancel: true,
    },
  ]}
>
  <div class="flex flex-row flex-wrap gap-2">
    {#each selected_spec_tags as tag}
      <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
        <span class="truncate">{tag}</span>
      </div>
    {/each}
  </div>
</Dialog>

<FilterTagsDialog
  bind:this={filter_tags_dialog}
  title="Filter Specs by Tags"
  {filter_tags}
  {available_filter_tags}
  onRemoveFilterTag={remove_filter_tag}
  onAddFilterTag={add_filter_tag}
/>

<AddTagsDialog
  bind:this={add_tags_dialog}
  title={selected_specs.size > 1
    ? "Add Tags to " + selected_specs.size + " Specs"
    : "Add Tags to Spec"}
  {project_id}
  {task_id}
  tag_type="task_run"
  bind:add_tags
  onTagsChanged={handle_tags_changed}
  onAddTags={add_selected_tags}
/>

<RemoveTagsDialog
  bind:this={remove_tags_dialog}
  title={selected_specs.size > 1
    ? "Remove Tags from " + selected_specs.size + " Specs"
    : "Remove Tags from Spec"}
  bind:remove_tags
  available_tags={removeable_tags}
  onRemoveTag={handle_remove_tag}
  onAddTagToRemove={handle_add_tag_to_remove}
  onRemoveTags={remove_selected_tags}
/>

<Dialog
  bind:this={archive_dialog}
  title={archive_action_state === "unarchive"
    ? selected_specs.size > 1
      ? `Unarchive ${selected_specs.size} Specs`
      : "Unarchive Spec"
    : selected_specs.size > 1
      ? `Archive ${selected_specs.size} Specs`
      : "Archive Spec"}
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: archive_action_state === "unarchive" ? "Unarchive" : "Archive",
      asyncAction: archive_selected_specs,
      isError: true,
    },
  ]}
>
  <div class="mt-6">
    <p class="text-sm text-gray-500 mt-2">
      {archive_action_state === "unarchive"
        ? "Unarchived specs will be set back to an active state."
        : "Archived specs will be hidden from this list but can be restored later by unarchiving them."}
    </p>
  </div>
</Dialog>

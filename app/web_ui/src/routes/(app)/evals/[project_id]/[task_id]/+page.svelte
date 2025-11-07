<script lang="ts">
  import AppPage from "../../../app_page.svelte"
  import EmptyEvaluator from "./empty_eval.svelte"
  import type { Eval } from "$lib/types"
  import { client } from "$lib/api_client"
  import { KilnError, createKilnError } from "$lib/utils/error_handlers"
  import { onMount, tick } from "svelte"
  import { goto } from "$app/navigation"
  import { page } from "$app/stores"
  import { load_model_info } from "$lib/stores"
  import { load_task_run_configs } from "$lib/stores/run_configs_store"
  import { formatDate } from "$lib/utils/formatters"
  import Dialog from "$lib/ui/dialog.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  $: project_id = $page.params.project_id
  $: task_id = $page.params.task_id

  let evals: Eval[] | null = null
  let evals_error: KilnError | null = null
  let evals_loading = true

  type EvalStatus = "Proposed" | "Active" | "Retired"
  type EvalPriority = "P1" | "P2" | "P3"
  type EvalProgress = "Not Started" | "In Progress" | "Complete" | "Deprecated"

  interface EvalWithMetadata extends Eval {
    status?: EvalStatus
    priority?: EvalPriority
    progress?: EvalProgress
    performance?: number | null
    tags?: string[]
  }

  let filter_tags: string[] = []
  let sortBy: "priority" | "progress" | "created_at" | "name" | "pass" | "" =
    "created_at"
  let sortDirection: "asc" | "desc" = "desc"
  let filter_tags_dialog: Dialog | null = null
  let use_chevron_priority_ui = true
  let use_circle_progress_ui = true
  let show_tags_column = true
  let editing_priority: string | null = null
  let editing_progress: string | null = null

  function startEditingPriority(evalId: string, event: MouseEvent) {
    event.stopPropagation()
    editing_priority = evalId
  }

  function startEditingProgress(evalId: string, event: MouseEvent) {
    event.stopPropagation()
    editing_progress = evalId
  }

  function updatePriority(evalId: string, newPriority: string) {
    if (evals) {
      const evalItem = evals.find((e) => e.id === evalId) as EvalWithMetadata
      if (evalItem) {
        evalItem.priority = newPriority as EvalPriority
        evals = [...evals]
      }
    }
    editing_priority = null
  }

  function updateProgress(evalId: string, newProgress: string) {
    if (evals) {
      const evalItem = evals.find((e) => e.id === evalId) as EvalWithMetadata
      if (evalItem) {
        evalItem.progress = newProgress as EvalProgress
        evals = [...evals]
      }
    }
    editing_progress = null
  }

  function getPriorityOrder(priority: EvalPriority | undefined): number {
    switch (priority) {
      case "P1":
        return 0
      case "P2":
        return 1
      case "P3":
        return 2
      default:
        return 3
    }
  }

  function getPriorityLabel(priority: EvalPriority | undefined): string {
    switch (priority) {
      case "P1":
        return "High"
      case "P2":
        return "Medium"
      case "P3":
        return "Low"
      default:
        return ""
    }
  }

  function getProgressOrder(progress: EvalProgress | undefined): number {
    switch (progress) {
      case "Deprecated":
        return 0
      case "Not Started":
        return 1
      case "In Progress":
        return 2
      case "Complete":
        return 3
      default:
        return 4
    }
  }

  function toggleSort(
    field: "priority" | "progress" | "created_at" | "name" | "pass",
  ) {
    if (sortBy === field) {
      sortDirection = sortDirection === "asc" ? "desc" : "asc"
    } else {
      sortBy = field
      sortDirection = "desc"
    }
  }

  function getAvailableFilterTags(
    filtered_evals: Eval[],
    filter_tags: string[],
  ): Record<string, number> {
    if (!filtered_evals) return {}

    const remaining_tags: Record<string, number> = {}
    filtered_evals.forEach((evaluator) => {
      const evalWithMeta = evaluator as EvalWithMetadata
      evalWithMeta.tags?.forEach((tag) => {
        if (filter_tags.includes(tag)) return
        if (typeof tag === "string") {
          remaining_tags[tag] = (remaining_tags[tag] || 0) + 1
        }
      })
    })
    return remaining_tags
  }

  $: available_filter_tags = getAvailableFilterTags(filtered_evals, filter_tags)

  function add_filter_tag(tag: string) {
    if (!filter_tags.includes(tag)) {
      filter_tags = [...filter_tags, tag]
    }
  }

  function remove_filter_tag(tag: string) {
    filter_tags = filter_tags.filter((t) => t !== tag)
  }

  function getEvalMeta(evaluator: Eval): EvalWithMetadata {
    return evaluator as EvalWithMetadata
  }

  $: is_empty = !evals || evals.length == 0

  $: filtered_evals = evals
    ? evals.filter((evaluator) => {
        const evalWithMeta = evaluator as EvalWithMetadata
        if (filter_tags.length === 0) return true
        return filter_tags.every((tag) => evalWithMeta.tags?.includes(tag))
      })
    : []

  $: sorted_evals = filtered_evals
    ? [...filtered_evals].sort((a, b) => {
        if (sortBy === "priority") {
          const aMeta = a as EvalWithMetadata
          const bMeta = b as EvalWithMetadata
          const priorityA = getPriorityOrder(aMeta.priority)
          const priorityB = getPriorityOrder(bMeta.priority)
          if (priorityA !== priorityB) {
            return sortDirection === "asc"
              ? priorityA - priorityB
              : priorityB - priorityA
          }
        } else if (sortBy === "progress") {
          const aMeta = a as EvalWithMetadata
          const bMeta = b as EvalWithMetadata
          const progressA = getProgressOrder(aMeta.progress)
          const progressB = getProgressOrder(bMeta.progress)
          if (progressA !== progressB) {
            return sortDirection === "asc"
              ? progressA - progressB
              : progressB - progressA
          }
        } else if (sortBy === "name") {
          const nameA = a.name || ""
          const nameB = b.name || ""
          if (nameA !== nameB) {
            return sortDirection === "asc"
              ? nameA.localeCompare(nameB)
              : nameB.localeCompare(nameA)
          }
        } else if (sortBy === "pass") {
          const aMeta = a as EvalWithMetadata
          const bMeta = b as EvalWithMetadata
          const passA =
            aMeta.progress === "Complete" &&
            aMeta.performance !== null &&
            aMeta.performance !== undefined
          const passB =
            bMeta.progress === "Complete" &&
            bMeta.performance !== null &&
            bMeta.performance !== undefined
          if (passA !== passB) {
            return sortDirection === "asc"
              ? (passA ? 1 : 0) - (passB ? 1 : 0)
              : (passB ? 1 : 0) - (passA ? 1 : 0)
          }
        } else if (sortBy === "created_at" || sortBy === "") {
          const dateA = a.created_at ? new Date(a.created_at).getTime() : 0
          const dateB = b.created_at ? new Date(b.created_at).getTime() : 0
          if (dateA !== dateB) {
            return sortDirection === "asc" ? dateA - dateB : dateB - dateA
          }
        }

        return (a.id || "").localeCompare(b.id || "")
      })
    : []

  onMount(async () => {
    // Wait for params to load
    await tick()
    // Usually cached and fast
    load_model_info()
    // Load the evals and run configs in parallel
    await Promise.all([get_evals(), get_task_run_configs()])
  })

  let run_configs_error: KilnError | null = null
  let run_configs_loading = true

  async function get_task_run_configs() {
    run_configs_loading = true
    try {
      await load_task_run_configs(project_id, task_id)
    } catch (err) {
      run_configs_error = createKilnError(err)
    } finally {
      run_configs_loading = false
    }
  }

  async function get_evals() {
    try {
      evals_loading = true
      const { data, error } = await client.GET(
        "/api/projects/{project_id}/tasks/{task_id}/evals",
        {
          params: {
            path: {
              project_id,
              task_id,
            },
          },
        },
      )
      if (error) {
        throw error
      }

      if (!data || data.length === 0) {
        evals = []
        return
      }

      const evalsWithMetadata = data.map((evaluator, index) => {
        let progress: EvalProgress
        let priority: EvalPriority

        if (index === 0) {
          progress = "Complete"
          priority = "P1"
        } else if (index === 1) {
          progress = "In Progress"
          priority = "P2"
        } else if (index === 2) {
          progress = "Not Started"
          priority = "P3"
        } else if (index === 3) {
          progress = "Deprecated"
          priority = "P3"
        } else {
          const hash = (str: string) => {
            let hash = 0
            for (let i = 0; i < str.length; i++) {
              const char = str.charCodeAt(i)
              hash = (hash << 5) - hash + char
              hash = hash & hash
            }
            return Math.abs(hash)
          }
          const evalId = evaluator.id || evaluator.name || ""
          const progresses: EvalProgress[] = [
            "Not Started",
            "In Progress",
            "Complete",
          ]
          const progressIndex = hash(evalId + "progress") % progresses.length
          progress = progresses[progressIndex]
          if (progress === "Complete") {
            priority = "P1"
          } else if (progress === "In Progress") {
            priority = "P2"
          } else {
            priority = "P3"
          }
        }

        const statuses: EvalStatus[] = ["Proposed", "Active", "Retired"]
        const hash = (str: string) => {
          let hash = 0
          for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i)
            hash = (hash << 5) - hash + char
            hash = hash & hash
          }
          return Math.abs(hash)
        }
        const evalId = evaluator.id || evaluator.name || ""
        const statusIndex = hash(evalId + "status") % statuses.length
        const sampleTags = [
          "production",
          "internal",
          "critical",
          "experimental",
          "beta",
          "stable",
          "test",
          "feature-flag",
        ]

        let tagCount: number
        if (index === 0) {
          tagCount = 3
        } else if (index === 1) {
          tagCount = 2
        } else if (index === 2) {
          tagCount = 1
        } else {
          tagCount = hash(evalId + "tags") % 5
        }

        const performance =
          progress === "Complete"
            ? Math.round(((hash(evalId + "perfval") % 100) / 100) * 100) / 100
            : null

        return {
          ...evaluator,
          status: statuses[statusIndex],
          priority: priority,
          progress: progress,
          performance: performance,
          tags: Array.from({ length: tagCount }, (_, i) => {
            const tagIndex = hash(evalId + `tag${i}`) % sampleTags.length
            return sampleTags[tagIndex]
          }).filter((tag, index, self) => self.indexOf(tag) === index),
        }
      })

      evals = evalsWithMetadata
    } catch (error) {
      evals_error = createKilnError(error)
    } finally {
      evals_loading = false
    }
  }

  $: loading = evals_loading || run_configs_loading
  $: error = evals_error || run_configs_error
</script>

<AppPage
  limit_max_width={true}
  title="Specs"
  subtitle="Define and evaluate desired model behaviors"
  sub_subtitle={is_empty ? undefined : "Read the Docs"}
  sub_subtitle_link="https://docs.kiln.tech/docs/evaluations"
  action_buttons={is_empty
    ? []
    : [
        {
          label: "New Spec",
          href: `/evals/${project_id}/${task_id}/create_evaluator`,
          primary: true,
        },
      ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if is_empty}
    <div class="flex flex-col items-center justify-center min-h-[60vh]">
      <EmptyEvaluator {project_id} {task_id} />
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if evals}
    <a href={`/evals/${project_id}/${task_id}/compare`} class="group">
      <div class="card border p-3 mb-4 rounded-md hover:bg-gray-50">
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
              >Find the best way to run this task by comparing models, prompts
              tools, and fine-tunes using evals, cost and performance.</span
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
      <div class="flex flex-row items-center justify-between">
        <div class="text-xl font-bold">All Specs</div>
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-mid !px-3"
            on:click={() => filter_tags_dialog?.show()}
          >
            <img alt="filter" src="/images/filter.svg" class="w-5 h-5" />
            {#if filter_tags.length > 0}
              <span class="badge badge-primary badge-sm"
                >{filter_tags.length}</span
              >
            {/if}
          </button>
        </div>
      </div>
    </div>
    <div class="overflow-x-auto rounded-lg border">
      <table class="table">
        <thead>
          <tr>
            <th
              class="hover:bg-base-200 cursor-pointer"
              on:click={() => toggleSort("name")}
            >
              Name
              {#if sortBy === "name"}
                {sortDirection === "asc" ? "▲" : "▼"}
              {/if}
            </th>
            <th>Description</th>
            {#if show_tags_column}
              <th class="text-right">Tags</th>
            {/if}
            <th
              class="hover:bg-base-200 cursor-pointer"
              on:click={() => toggleSort("priority")}
            >
              Priority
              {#if sortBy === "priority"}
                {sortDirection === "asc" ? "▲" : "▼"}
              {/if}
            </th>
            <th
              class="hover:bg-base-200 cursor-pointer"
              on:click={() => toggleSort("progress")}
            >
              Status
              {#if sortBy === "progress"}
                {sortDirection === "asc" ? "▲" : "▼"}
              {/if}
            </th>
            <th class="text-center">
              <div class="flex items-center justify-center gap-1">
                <span class="inline-flex items-center">Score</span>
                <span class="inline-flex items-center">
                  <InfoTooltip
                    tooltip_text={'Score using your task\'s default run configuration - "Magical Falcon"'}
                    position="top"
                    no_pad={true}
                  />
                </span>
              </div>
            </th>
            <th
              class="hover:bg-base-200 cursor-pointer text-center"
              on:click={() => toggleSort("pass")}
            >
              <div class="flex items-center justify-center gap-1">
                <span class="inline-flex items-center">Pass</span>
                <span class="inline-flex items-center">
                  <InfoTooltip
                    tooltip_text="Comparing score to your spec's defined threshold"
                    position="top"
                    no_pad={true}
                  />
                </span>
                {#if sortBy === "pass"}
                  <span>{sortDirection === "asc" ? "▲" : "▼"}</span>
                {/if}
              </div>
            </th>
            <th
              class="hover:bg-base-200 cursor-pointer text-center"
              on:click={() => toggleSort("created_at")}
            >
              Created At
              {#if sortBy === "created_at"}
                {sortDirection === "asc" ? "▲" : "▼"}
              {/if}
            </th>
          </tr>
        </thead>
        <tbody>
          {#each sorted_evals as evaluator}
            {@const evalMeta = getEvalMeta(evaluator)}
            <tr
              class="hover cursor-pointer"
              on:click={() => {
                goto(`/evals/${project_id}/${task_id}/${evaluator.id}`)
              }}
            >
              <td>{evaluator.name}</td>
              <td>
                <span
                  class="truncate tooltip tooltip-top {evaluator.description
                    ? ''
                    : 'text-gray-500'}"
                  data-tip={evaluator.description || undefined}
                >
                  {evaluator.description || "-"}
                </span>
              </td>
              {#if show_tags_column}
                <td class="text-right">
                  {#if evalMeta.tags && evalMeta.tags.length > 0}
                    {@const sortedTags = [...evalMeta.tags].sort()}
                    {@const firstTag = sortedTags[0]}
                    {@const remainingCount = sortedTags.length - 1}
                    {@const maxTagLength = 20}
                    {@const othersText =
                      remainingCount > 0
                        ? ` +${remainingCount} ${
                            remainingCount === 1 ? "other" : "others"
                          }`
                        : ""}
                    {@const fullText = firstTag + othersText}
                    {@const truncatedText =
                      fullText.length > maxTagLength
                        ? fullText.slice(0, maxTagLength) + "..."
                        : fullText}
                    <span
                      class="badge bg-gray-200 text-gray-500 py-3 px-3 tooltip tooltip-top cursor-default flex items-center justify-center ml-auto w-fit max-w-[200px]"
                      data-tip={sortedTags.join(", ")}
                    >
                      <span class="truncate">{truncatedText}</span>
                    </span>
                  {:else}
                    <span class="text-gray-500">-</span>
                  {/if}
                </td>
              {/if}
              <td class="text-center">
                {#if editing_priority === evaluator.id}
                  <select
                    class="select select-sm select-bordered w-auto mx-auto"
                    value={evalMeta.priority || "P3"}
                    on:change={(e) => {
                      if (evaluator.id) {
                        updatePriority(evaluator.id, e.currentTarget.value)
                      }
                    }}
                    on:blur={() => {
                      editing_priority = null
                    }}
                    on:click|stopPropagation
                  >
                    <option value="P1">High</option>
                    <option value="P2">Medium</option>
                    <option value="P3">Low</option>
                  </select>
                {:else if evalMeta.priority}
                  {#if use_chevron_priority_ui}
                    {@const isP1 = evalMeta.priority === "P1"}
                    {@const isP2 = evalMeta.priority === "P2"}
                    {@const isP3 = evalMeta.priority === "P3"}
                    <div
                      class="flex justify-center tooltip tooltip-top cursor-pointer hover:opacity-70"
                      data-tip={getPriorityLabel(evalMeta.priority)}
                      on:click={(e) => {
                        if (evaluator.id) {
                          startEditingPriority(evaluator.id, e)
                        }
                      }}
                    >
                      <svg
                        class="w-4 h-4"
                        viewBox="0 0 16 16"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        <path
                          d="m 1 10 c -0.554688 0 -1 0.445312 -1 1 v 4 c 0 0.554688 0.445312 1 1 1 h 1 c 0.554688 0 1 -0.445312 1 -1 v -4 c 0 -0.554688 -0.445312 -1 -1 -1 z m 0 0"
                          fill={isP1 || isP2 || isP3
                            ? "currentColor"
                            : "#9CA3AF"}
                        />
                        <path
                          d="m 5 6 c -0.554688 0 -1 0.445312 -1 1 v 8 c 0 0.554688 0.445312 1 1 1 h 1 c 0.554688 0 1 -0.445312 1 -1 v -8 c 0 -0.554688 -0.445312 -1 -1 -1 z m 0 0"
                          fill={isP1 || isP2 ? "currentColor" : "#9CA3AF"}
                        />
                        <path
                          d="m 9 2 c -0.554688 0 -1 0.445312 -1 1 v 12 c 0 0.554688 0.445312 1 1 1 h 1 c 0.554688 0 1 -0.445312 1 -1 v -12 c 0 -0.554688 -0.445312 -1 -1 -1 z m 0 0"
                          fill={isP1 ? "currentColor" : "#9CA3AF"}
                        />
                      </svg>
                    </div>
                  {:else}
                    <span
                      class="badge tooltip tooltip-top cursor-pointer hover:opacity-70"
                      data-tip={getPriorityLabel(evalMeta.priority)}
                      style="background-color: {evalMeta.priority === 'P1'
                        ? '#FDECEA'
                        : evalMeta.priority === 'P2'
                          ? '#FFF6E5'
                          : '#E8FAF1'}; color: {evalMeta.priority === 'P1'
                        ? '#B42318'
                        : evalMeta.priority === 'P2'
                          ? '#B93815'
                          : '#027A48'}"
                      on:click={(e) => {
                        if (evaluator.id) {
                          startEditingPriority(evaluator.id, e)
                        }
                      }}
                    >
                      {evalMeta.priority}
                    </span>
                  {/if}
                {:else}
                  <span class="text-gray-500">-</span>
                {/if}
              </td>
              <td class="text-center">
                {#if editing_progress === evaluator.id}
                  <select
                    class="select select-sm select-bordered w-auto mx-auto"
                    value={evalMeta.progress || "Not Started"}
                    on:change={(e) => {
                      if (evaluator.id) {
                        updateProgress(evaluator.id, e.currentTarget.value)
                      }
                    }}
                    on:blur={() => {
                      editing_progress = null
                    }}
                    on:click|stopPropagation
                  >
                    <option value="Not Started">Not Started</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Complete">Complete</option>
                    <option value="Deprecated">Deprecated</option>
                  </select>
                {:else if evalMeta.progress}
                  {#if use_circle_progress_ui}
                    <div
                      class="flex justify-center tooltip tooltip-top cursor-pointer hover:opacity-70"
                      data-tip={evalMeta.progress}
                      on:click={(e) => {
                        if (evaluator.id) {
                          startEditingProgress(evaluator.id, e)
                        }
                      }}
                    >
                      <svg
                        class="w-5 h-5"
                        viewBox="0 0 24 24"
                        fill="none"
                        xmlns="http://www.w3.org/2000/svg"
                      >
                        {#if evalMeta.progress === "Not Started"}
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            stroke-width="1.5"
                            stroke-dasharray="1.5 1.64"
                            fill="none"
                          />
                        {:else if evalMeta.progress === "In Progress"}
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            stroke-width="1.5"
                            fill="none"
                          />
                          <path
                            d="M 12 3.5 A 8.5 8.5 0 0 1 12 20.5 L 12 12 Z"
                            fill="#9CA3AF"
                          />
                        {:else if evalMeta.progress === "Complete"}
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            stroke-width="1.5"
                            fill="none"
                          />
                          <path
                            d="M8.5 12.5L10.5 14.5L15.5 9.5"
                            stroke="#9CA3AF"
                            stroke-width="1.5"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            fill="none"
                          />
                        {:else if evalMeta.progress === "Deprecated"}
                          <circle
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            stroke-width="1.5"
                            fill="none"
                          />
                          <path
                            d="M9 9L15 15M15 9L9 15"
                            stroke="#9CA3AF"
                            stroke-width="1.5"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                          />
                        {/if}
                      </svg>
                    </div>
                  {:else}
                    <span
                      class="tooltip tooltip-top cursor-pointer hover:opacity-70"
                      data-tip={evalMeta.progress}
                      on:click={(e) => {
                        if (evaluator.id) {
                          startEditingProgress(evaluator.id, e)
                        }
                      }}>{evalMeta.progress}</span
                    >
                  {/if}
                {:else}
                  <span class="text-gray-500">-</span>
                {/if}
              </td>
              <td class="text-center">
                {#if evalMeta.progress === "Complete"}
                  <span class="font-medium">
                    {evalMeta.performance !== null &&
                    evalMeta.performance !== undefined
                      ? evalMeta.performance.toFixed(2)
                      : "0.00"}
                  </span>
                {:else}
                  <span class="text-gray-500">-</span>
                {/if}
              </td>
              <td class="text-center">
                {#if evalMeta.progress === "Complete" && evalMeta.performance !== null && evalMeta.performance !== undefined}
                  <svg
                    class="w-5 h-5 text-success mx-auto"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                {:else}
                  <span class="text-gray-500">-</span>
                {/if}
              </td>
              <td class="text-center">{formatDate(evaluator.created_at)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <Dialog
      bind:this={filter_tags_dialog}
      title="Filter Specs by Tags"
      action_buttons={[{ label: "Close", isCancel: true }]}
    >
      {#if filter_tags.length > 0}
        <div class="text-sm mb-2 font-medium">Current Filters:</div>
      {/if}
      <div class="flex flex-row gap-2 flex-wrap">
        {#each filter_tags as tag}
          <div class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full">
            <span class="truncate">{tag}</span>
            <button
              class="pl-3 font-medium shrink-0"
              on:click={() => remove_filter_tag(tag)}>✕</button
            >
          </div>
        {/each}
      </div>

      <div class="text-sm mt-4 mb-2 font-medium">Add a filter:</div>
      {#if Object.keys(available_filter_tags).length == 0}
        <p class="text-sm text-gray-500">
          Any further filters would show zero results.
        </p>
      {/if}
      <div class="flex flex-row gap-2 flex-wrap">
        {#each Object.entries(available_filter_tags).sort((a, b) => b[1] - a[1]) as [tag, count]}
          <button
            class="badge bg-gray-200 text-gray-500 py-3 px-3 max-w-full"
            on:click={() => add_filter_tag(tag)}>{tag} ({count})</button
          >
        {/each}
      </div>
    </Dialog>
  {/if}
</AppPage>

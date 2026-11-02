<script lang="ts">
  import { tick } from "svelte"
  import { page } from "$app/stores"
  import { goto } from "$app/navigation"
  import { agentInfo } from "$lib/agent"
  import {
    available_tools,
    get_task_composite_id,
    load_available_tools,
    load_model_info,
    model_info,
  } from "$lib/stores"
  import {
    load_task_prompts,
    prompts_by_task_composite_id,
  } from "$lib/stores/prompts_store"
  import {
    load_task_run_configs,
    run_configs_by_task_composite_id,
  } from "$lib/stores/run_configs_store"
  import ForkIcon from "$lib/ui/icons/fork_icon.svelte"
  import Intro from "$lib/ui/intro.svelte"
  import { createKilnError, type KilnError } from "$lib/utils/error_handlers"
  import { experiment_lineage_link } from "$lib/utils/link_builder"
  import type { DisplayContext } from "$lib/utils/lineage/lineage_display"
  import {
    build_lineage_graph,
    summarize_lineage,
    type FilterKey,
  } from "$lib/utils/lineage/lineage_graph"
  import { layout_lineage } from "$lib/utils/lineage/lineage_layout"
  import AppPage from "../../../../app_page.svelte"
  import LineageCanvas from "./lineage_canvas.svelte"
  import LineageFilterChips from "./lineage_filter_chips.svelte"
  import LineagePanel from "./lineage_panel.svelte"
  import { closes_panel } from "./panel_close_key"

  // Below this the body stacks and the graph keeps a fixed height.
  const WIDE_LAYOUT_QUERY = "(min-width: 1024px)"
  const MIN_BODY_HEIGHT_PX = 420
  // The body's lg:-mb-8 cancels 32px of AppPage's mb-12, so the gap under it
  // is 48px, the same as the card's md:px-12 side gutter. Below the body: the
  // rest of mb-12 (16px), plus the app layout's pb-8, 1px border and mb-4.
  const SPACE_BELOW_BODY_PX = 65

  $: project_id = $page.params.project_id!
  $: task_id = $page.params.task_id!

  let loading = true
  let error: KilnError | null = null
  let filters: Set<FilterKey> = new Set()
  let selected_id: string | null = null
  let initial_center_id: string | null = null
  let canvas: LineageCanvas | null = null
  let panel_el: HTMLDivElement | null = null
  let latest_load_id = 0

  $: if (project_id && task_id) {
    load_page_data(project_id, task_id)
  }

  // Only the latest load may restore the selection, set an error or clear
  // loading. Going to another task and back leaves this task's earlier load
  // still running.
  async function load_page_data(req_project_id: string, req_task_id: string) {
    const load_id = ++latest_load_id
    loading = true
    error = null
    selected_id = null
    initial_center_id = null
    load_available_tools(req_project_id)
    try {
      await Promise.all([
        load_model_info(),
        load_task_prompts(req_project_id, req_task_id),
        load_task_run_configs(req_project_id, req_task_id, true),
      ])
      await tick()
      if (load_id !== latest_load_id) return
      restore_selection()
    } catch (e) {
      if (load_id !== latest_load_id) return
      error = createKilnError(e)
    } finally {
      if (load_id === latest_load_id) {
        loading = false
      }
    }
  }

  function restore_selection() {
    const id = $page.url.searchParams.get("selected")
    if (id && graph.nodes.has(id)) {
      selected_id = id
      initial_center_id = id
    }
  }

  function on_window_keydown(event: KeyboardEvent) {
    if (selected_id !== null && closes_panel(event)) {
      close_panel()
    }
  }

  // Closing the panel removes the focused element with it, so focus moves to
  // the graph rather than falling back to the page.
  function close_panel() {
    const focus_was_in_panel =
      panel_el?.contains(document.activeElement) ?? false
    select(null)
    if (focus_was_in_panel) {
      canvas?.focus_graph()
    }
  }

  function select(id: string | null) {
    selected_id = id
    goto(experiment_lineage_link(project_id, task_id, id), {
      replaceState: true,
      noScroll: true,
      keepFocus: true,
    })
  }

  $: configs =
    $run_configs_by_task_composite_id[
      get_task_composite_id(project_id, task_id)
    ] ?? []
  $: graph = build_lineage_graph(configs)
  $: layout = layout_lineage(graph)
  $: summary = summarize_lineage(graph)
  let ctx: DisplayContext
  $: ctx = {
    project_id,
    task_id,
    model_info: $model_info,
    task_prompts:
      $prompts_by_task_composite_id[
        get_task_composite_id(project_id, task_id)
      ] ?? null,
    project_tools: $available_tools[project_id] ?? null,
  }
  $: selected_node = selected_id ? graph.nodes.get(selected_id) ?? null : null
  $: if (!loading && selected_id && !selected_node) {
    select(null)
  }
  $: empty_state =
    summary.run_config_count === 0
      ? {
          title: "No Run Configurations Yet",
          paragraphs: [
            "A run configuration is one way to run this task: a model, a prompt, tools and settings. Each one you clone or derive from another is linked to it, so this page can show how your agent evolved and what changed at each step.",
          ],
          action_buttons: [
            {
              label: "Create Run Config",
              href: `/optimize/${project_id}/${task_id}/run_config/create`,
              is_primary: true,
            },
          ],
        }
      : graph.edges.length === 0
        ? {
            title: "No Experiment Lineage",
            paragraphs: [
              "Lineage is recorded when you clone a run config, or when an agent derives one from another.",
              "No run config in this task has a parent.",
            ],
            action_buttons: [],
          }
        : null
  $: stats = [
    {
      count: summary.run_config_count,
      label: ["config", "configs"],
      always_shown: true,
    },
    {
      count: summary.model_count,
      label: ["model", "models"],
      always_shown: true,
    },
    {
      count: summary.tool_count,
      label: ["tool", "tools"],
      always_shown: false,
    },
    {
      count: summary.skill_count,
      label: ["skill", "skills"],
      always_shown: false,
    },
  ].filter((stat) => stat.always_shown || stat.count > 0)

  // A new selection shows its panel from the top, not at the previous one's
  // scroll position.
  $: scroll_panel_to_top(selected_id)

  function scroll_panel_to_top(_: string | null) {
    if (panel_el) {
      panel_el.scrollTop = 0
    }
  }

  $: agentInfo.set({
    name: "Experiment Lineage",
    description: `Experiment lineage graph for project ID ${project_id}, task ID ${task_id}. Shows every run configuration for the task (total count ${summary.run_config_count}) as a tree, each linked to the run config it was derived from and marked with what changed from that parent.${selected_node ? ` Selected run config ID: ${selected_node.id}.` : ""}`,
  })

  let body_el: HTMLDivElement | null = null
  let body_height: number | null = null

  function measure_body() {
    if (!body_el || !window.matchMedia(WIDE_LAYOUT_QUERY).matches) {
      body_height = null
      return
    }
    const top = body_el.getBoundingClientRect().top + window.scrollY
    body_height = Math.max(
      MIN_BODY_HEIGHT_PX,
      window.innerHeight - top - SPACE_BELOW_BODY_PX,
    )
  }

  // The body's top moves when content above it resizes, such as chips wrapping.
  // Measuring a frame later keeps the height change out of the observer's
  // callback, where the browser would report a resize loop.
  function remeasure_on_container_resize(body: HTMLElement) {
    let frame: number | null = null
    const observer = new ResizeObserver(() => {
      if (frame !== null) {
        cancelAnimationFrame(frame)
      }
      frame = requestAnimationFrame(() => {
        frame = null
        measure_body()
      })
    })
    if (body.parentElement) {
      observer.observe(body.parentElement)
    }
    return {
      destroy() {
        observer.disconnect()
        if (frame !== null) {
          cancelAnimationFrame(frame)
        }
      },
    }
  }
</script>

<svelte:window on:resize={measure_body} on:keydown={on_window_keydown} />

<AppPage
  title="Experiment Lineage"
  subtitle="Every run configuration for this task, and how they evolved."
  breadcrumbs={[
    { label: "Optimize", href: `/optimize/${project_id}/${task_id}` },
  ]}
>
  {#if loading}
    <div class="w-full min-h-[50vh] flex justify-center items-center">
      <div class="loading loading-spinner loading-lg"></div>
    </div>
  {:else if error}
    <div
      class="w-full min-h-[50vh] flex flex-col justify-center items-center gap-2"
    >
      <div class="font-medium">Error Loading Run Configurations</div>
      <div class="text-error text-sm">
        {error.getMessage() || "An unknown error occurred"}
      </div>
    </div>
  {:else if empty_state}
    <div class="flex flex-col items-center justify-center min-h-[50vh]">
      <Intro
        title={empty_state.title}
        description_paragraphs={empty_state.paragraphs}
        action_buttons={empty_state.action_buttons}
      >
        <div slot="icon">
          <div class="h-12 w-12">
            <ForkIcon />
          </div>
        </div>
      </Intro>
    </div>
  {:else}
    <div class="flex flex-col gap-6">
      <div class="flex gap-10">
        {#each stats as stat}
          <div class="flex flex-col">
            <div class="text-xl font-medium tabular-nums">{stat.count}</div>
            <div class="text-sm text-gray-500">
              {stat.count === 1 ? stat.label[0] : stat.label[1]}
            </div>
          </div>
        {/each}
      </div>
      <LineageFilterChips
        bind:active={filters}
        counts={summary.filter_counts}
      />
      <div
        bind:this={body_el}
        use:remeasure_on_container_resize
        class="flex flex-col lg:flex-row gap-6 lg:-mb-8"
        style={body_height === null ? undefined : `height: ${body_height}px;`}
      >
        <div class="h-[480px] lg:h-auto lg:flex-1 min-w-0">
          <LineageCanvas
            bind:this={canvas}
            {graph}
            {layout}
            {filters}
            {selected_id}
            {initial_center_id}
            model_info={$model_info}
            on:select={(event) => select(event.detail)}
            on:close={() => select(null)}
          />
        </div>
        {#if selected_node}
          <div
            bind:this={panel_el}
            class="lg:w-[360px] lg:flex-none lg:overflow-y-auto"
          >
            <LineagePanel
              node={selected_node}
              {graph}
              {ctx}
              available_tools={$available_tools}
              on:select={(event) => select(event.detail)}
              on:close={close_panel}
            />
          </div>
        {/if}
      </div>
    </div>
  {/if}
</AppPage>

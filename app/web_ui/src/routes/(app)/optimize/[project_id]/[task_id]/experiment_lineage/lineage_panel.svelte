<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import { goto } from "$app/navigation"
  import type { ToolSetApiDescription } from "$lib/types"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import Output from "$lib/ui/output.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import { get_provider_image } from "$lib/ui/provider_image"
  import InputTransformModal from "$lib/ui/run_config_component/input_transform_modal.svelte"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import { compare_run_configs_link } from "$lib/utils/link_builder"
  import {
    change_rows,
    lineage_line_parts,
    node_title,
    origin_text,
    type DisplayContext,
  } from "$lib/utils/lineage/lineage_display"
  import type {
    LineageGraph,
    LineageNode,
  } from "$lib/utils/lineage/lineage_graph"
  import { CHANGE_KIND_LABELS, GLYPH } from "$lib/utils/lineage/lineage_glyph"
  import {
    getRunConfigInputTransform,
    getRunConfigUiProperties,
  } from "$lib/utils/run_config_formatters"
  import LineageSwatch from "./lineage_swatch.svelte"

  export let project_id: string
  export let task_id: string
  export let node: LineageNode
  export let graph: LineageGraph
  export let ctx: DisplayContext
  export let available_tools: Record<string, ToolSetApiDescription[]>

  const dispatch = createEventDispatcher<{ select: string; close: null }>()

  let input_transform_modal: InputTransformModal | null = null

  $: config = node.config
  $: title = node_title(node)
  $: lineage_parts = lineage_line_parts(node, graph)
  $: primary_parent_id = node.parent_ids[0] ?? null
  $: parent_config = primary_parent_id
    ? graph.nodes.get(primary_parent_id)?.config ?? null
    : null
  $: rows =
    config && parent_config && node.status.type === "changed"
      ? change_rows(parent_config, config, node.status.kinds, ctx)
      : []
  $: notes = config?.provenance?.notes ?? null
  $: created_by = origin_text(config?.provenance?.origin)
  $: input_transform = config ? getRunConfigInputTransform(config) : null
  $: properties = config
    ? getRunConfigUiProperties(
        project_id,
        task_id,
        config,
        ctx.model_info,
        ctx.task_prompts,
        available_tools,
        () => input_transform_modal?.show(),
      )
    : []

  function compare() {
    goto(compare_run_configs_link(project_id, task_id, [node.id, null]))
  }

  function compare_to_parent() {
    if (primary_parent_id) {
      goto(
        compare_run_configs_link(project_id, task_id, [
          primary_parent_id,
          node.id,
        ]),
      )
    }
  }
</script>

<div class="flex flex-col gap-6">
  <div class="flex items-start gap-3">
    <LineageSwatch status={node.status} glyph={GLYPH.panel} />
    <div class="flex flex-col min-w-0 grow">
      <div class="text-lg font-medium truncate" {title}>{title}</div>
      <div class="text-sm text-gray-500" data-testid="lineage-panel-line">
        {#each lineage_parts as part}{#if part.type === "link"}<button
              type="button"
              class="link"
              on:click={() => dispatch("select", part.node_id)}
              >{part.text}</button
            >{:else}{part.text}{/if}{/each}
      </div>
    </div>
    <button
      type="button"
      class="btn btn-sm h-8 w-8 btn-circle btn-ghost focus:outline-none flex-none"
      aria-label="Close details"
      on:click={() => dispatch("close")}
    >
      <span class="h-6 w-6 block"><CloseIcon /></span>
    </button>
  </div>

  {#if node.status.type === "changed" || node.status.type === "copy" || node.status.type === "parent_deleted"}
    <div class="flex flex-col gap-4">
      <SettingsHeader title="Changed from Parent" />
      {#if node.status.type === "copy"}
        <div class="text-sm">Same settings as parent.</div>
      {:else if node.status.type === "parent_deleted"}
        <div class="text-sm">
          The parent run config was deleted, so changes can't be shown.
        </div>
      {:else}
        <div
          class="grid grid-cols-[12px_auto_1fr] gap-x-3 gap-y-2 text-sm"
          data-testid="lineage-change-rows"
        >
          {#each rows as row}
            <div class="pt-1">
              <LineageSwatch
                status={{ type: "changed", kinds: [row.kind] }}
                glyph={GLYPH.swatch}
              />
            </div>
            <div class="text-gray-500">{CHANGE_KIND_LABELS[row.kind]}</div>
            <div class="flex flex-col min-w-0 break-words">
              <div class="font-medium flex items-center gap-1">
                {#if row.provider_id}
                  <img
                    src={get_provider_image(row.provider_id)}
                    alt=""
                    class="w-3.5 h-3.5 flex-none"
                  />
                {/if}
                <span class="min-w-0">{row.value}</span>
              </div>
              <div class="text-xs text-gray-500 line-through">
                {row.previous}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}

  {#if notes}
    <div class="flex flex-col gap-4">
      <SettingsHeader title="Notes" />
      <Output raw_output={notes} />
      {#if created_by}
        <div class="text-sm text-gray-500">{created_by}</div>
      {/if}
    </div>
  {/if}

  {#if config}
    <div class="flex flex-col gap-4">
      <SettingsHeader title="Run Configuration" />
      <PropertyList {properties} />
    </div>

    <div class="grid grid-cols-2 gap-2">
      <button type="button" class="btn btn-mid" on:click={compare}>
        Compare
      </button>
      {#if parent_config}
        <button type="button" class="btn btn-mid" on:click={compare_to_parent}>
          Compare to Parent
        </button>
      {/if}
    </div>
  {/if}
</div>

{#if input_transform}
  <InputTransformModal
    bind:this={input_transform_modal}
    transform={input_transform}
  />
{/if}

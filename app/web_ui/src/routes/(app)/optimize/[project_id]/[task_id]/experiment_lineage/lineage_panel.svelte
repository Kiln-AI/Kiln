<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import type { ToolSetApiDescription } from "$lib/types"
  import Dialog from "$lib/ui/dialog.svelte"
  import CloseIcon from "$lib/ui/icons/close_icon.svelte"
  import Output from "$lib/ui/output.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import InputTransformModal from "$lib/ui/run_config_component/input_transform_modal.svelte"
  import { compare_run_configs_link } from "$lib/utils/link_builder"
  import {
    added_removed_text,
    change_rows,
    lineage_relatives,
    lineage_summary_text,
    node_title,
    origin_text,
    type ChangeRow,
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
  import LineageLinkedText from "./lineage_linked_text.svelte"
  import LineagePanelSection from "./lineage_panel_section.svelte"
  import LineageSwatch from "./lineage_swatch.svelte"

  export let node: LineageNode
  export let graph: LineageGraph
  export let ctx: DisplayContext
  export let available_tools: Record<string, ToolSetApiDescription[]>

  const dispatch = createEventDispatcher<{ select: string; close: null }>()

  type ListRow = Extract<ChangeRow, { type: "list" }>

  let input_transform_modal: InputTransformModal | null = null
  let lineage_dialog: Dialog | null = null
  let lineage_opener: HTMLButtonElement | null = null
  let list_dialog: Dialog | null = null
  let list_opener: HTMLElement | null = null
  let list_row: ListRow | null = null

  $: config = node.config
  $: title = node_title(node)
  $: summary = lineage_summary_text(node)
  $: relatives = lineage_relatives(node, graph)
  $: has_relatives =
    relatives.parents.length > 0 || relatives.children.length > 0
  $: primary_parent_id = node.parent_ids[0] ?? null
  $: parent_config = primary_parent_id
    ? graph.nodes.get(primary_parent_id)?.config ?? null
    : null
  $: rows =
    config && parent_config && node.status.type === "changed"
      ? change_rows(parent_config, config, node.status.kinds, ctx)
      : []
  $: change_properties = rows.map(
    (row): UiProperty => ({
      name: CHANGE_KIND_LABELS[row.kind],
      value: "",
      use_custom_slot: true,
    }),
  )
  $: notes = config?.provenance?.notes ?? null
  $: creator = origin_text(config?.provenance?.origin)
  $: input_transform = config ? getRunConfigInputTransform(config) : null
  $: properties = config
    ? getRunConfigUiProperties(
        ctx.project_id,
        ctx.task_id,
        config,
        ctx.model_info,
        ctx.task_prompts,
        available_tools,
        () => input_transform_modal?.show(),
      )
    : []

  function row_named(name: string): ChangeRow | undefined {
    return rows.find((row) => CHANGE_KIND_LABELS[row.kind] === name)
  }

  function select_relative(id: string) {
    lineage_dialog?.close()
    dispatch("select", id)
  }

  function open_list_dialog(row: ListRow, event: MouseEvent) {
    list_row = row
    list_opener = event.currentTarget as HTMLElement
    list_dialog?.show()
  }
</script>

<div class="flex flex-col gap-8">
  <div class="flex items-start gap-3">
    <LineageSwatch status={node.status} glyph={GLYPH.panel} />
    <div class="flex flex-col gap-1 min-w-0 grow">
      <div class="text-xl font-bold line-clamp-2 break-words" {title}>
        {title}
      </div>
      {#if has_relatives}
        <button
          type="button"
          class="link text-sm text-gray-500 text-left self-start"
          data-testid="lineage-panel-line"
          bind:this={lineage_opener}
          on:click={() => lineage_dialog?.show()}>{summary}</button
        >
      {:else}
        <div class="text-sm text-gray-500" data-testid="lineage-panel-line">
          {summary}
        </div>
      {/if}
      {#if creator}
        <span class="badge badge-outline badge-primary badge-sm self-start mt-1"
          >{creator}</span
        >
      {/if}
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

  {#if notes}
    <LineagePanelSection title="Notes">
      <Output raw_output={notes} />
    </LineagePanelSection>
  {/if}

  {#if node.status.type === "changed" || node.status.type === "copy" || node.status.type === "parent_deleted"}
    <LineagePanelSection title="Changed from Parent">
      {#if node.status.type === "copy"}
        <div class="text-sm">Same settings as parent.</div>
      {:else if node.status.type === "parent_deleted"}
        <div class="text-sm">
          The parent run config was deleted, so changes can't be shown.
        </div>
      {:else}
        <div data-testid="lineage-change-rows">
          <PropertyList properties={change_properties}>
            <svelte:fragment slot="custom_value" let:property>
              {@const row = row_named(property.name)}
              {#if row?.type === "value"}
                <div class="flex flex-col min-w-0 w-full">
                  <div class="truncate" title={row.value.text}>
                    <LineageLinkedText value={row.value} />
                  </div>
                  <div
                    class="truncate text-xs font-light"
                    title="was {row.previous.text}"
                    data-testid="lineage-change-previous"
                  >
                    was <LineageLinkedText value={row.previous} />
                  </div>
                </div>
              {:else if row?.type === "list"}
                {@const list = row}
                <button
                  type="button"
                  class="link text-left"
                  on:click={(event) => open_list_dialog(list, event)}
                  >{added_removed_text(
                    row.added.length,
                    row.removed.length,
                  )}</button
                >
              {/if}
            </svelte:fragment>
          </PropertyList>
        </div>
      {/if}
    </LineagePanelSection>
  {/if}

  {#if config}
    <LineagePanelSection title="Run Configuration">
      <a
        slot="subtitle"
        href={compare_run_configs_link(ctx.project_id, ctx.task_id, [
          node.id,
          null,
        ])}
        class="link text-sm text-gray-500 self-start"
        >Compare eval results to others</a
      >
      <PropertyList {properties} />
    </LineagePanelSection>
  {/if}
</div>

<Dialog
  bind:this={lineage_dialog}
  title="Lineage"
  subtitle={title}
  action_buttons={[{ label: "Close", isCancel: true }]}
  on:close={() => lineage_opener?.focus()}
>
  <div class="flex flex-col gap-6 text-sm">
    {#each [{ heading: "Parents", items: relatives.parents }, { heading: "Children", items: relatives.children }] as group}
      {#if group.items.length > 0}
        <div class="flex flex-col gap-2">
          <div class="font-medium">{group.heading}</div>
          <ul class="flex flex-col gap-2" aria-label={group.heading}>
            {#each group.items as relative (relative.id)}
              {@const relative_node = graph.nodes.get(relative.id)}
              <li class="flex items-center gap-2 min-w-0">
                {#if relative_node}
                  <LineageSwatch
                    status={relative_node.status}
                    glyph={GLYPH.swatch}
                  />
                {/if}
                {#if relative.deleted}
                  <span class="truncate text-gray-500">{relative.text}</span>
                {:else}
                  <button
                    type="button"
                    class="link truncate text-left min-w-0"
                    title={relative.text}
                    on:click={() => select_relative(relative.id)}
                    >{relative.text}</button
                  >
                {/if}
              </li>
            {/each}
          </ul>
        </div>
      {/if}
    {/each}
  </div>
</Dialog>

<Dialog
  bind:this={list_dialog}
  title={list_row ? `${CHANGE_KIND_LABELS[list_row.kind]} Changed` : ""}
  subtitle="Compared with the parent run configuration."
  action_buttons={[{ label: "Close", isCancel: true }]}
  on:close={() => list_opener?.focus()}
>
  {#if list_row}
    <div class="flex flex-col gap-6 text-sm">
      {#each [{ heading: "Added", items: list_row.added }, { heading: "Removed", items: list_row.removed }] as group}
        {#if group.items.length > 0}
          <div class="flex flex-col gap-2">
            <div class="font-medium">{group.heading}</div>
            <ul class="flex flex-col gap-2" aria-label={group.heading}>
              {#each group.items as item}
                <li class="truncate" title={item.text}>
                  <LineageLinkedText value={item} />
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      {/each}
    </div>
  {/if}
</Dialog>

{#if input_transform}
  <InputTransformModal
    bind:this={input_transform_modal}
    transform={input_transform}
  />
{/if}

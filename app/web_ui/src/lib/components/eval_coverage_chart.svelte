<script lang="ts">
  import type {
    CoverageData,
    CoverageNode,
  } from "$lib/utils/eval_coverage/eval_coverage_data"
  import { packWeighted } from "$lib/utils/eval_coverage/circle_pack"
  import { principleGroups } from "$lib/utils/eval_coverage/constitution"
  import { formatPriority } from "$lib/utils/formatters"
  import SettingsHeader from "$lib/ui/settings_header.svelte"

  /**
   * Eval coverage chart.
   *
   * One large circle is the whole product. Inside it, one circle per eval,
   * packed tightly: area is the share of the constitution the eval holds,
   * fill is its pass rate. Dashed circles are planned evals; dotted circles
   * are principles with no eval, and open the eval builder. The ring around
   * the outside has one arc per principle of the constitution, grouped by
   * the value each serves; an arc's length is the principle's importance
   * and its tint is the pass rate of the evals that judge it. Hovering
   * links the ring and the circles.
   */

  export let data: CoverageData
  /** True while pass rates are loading: the chart holds at reduced opacity. */
  export let loading = false

  // Geometry in viewBox units.
  const R = 100 // packing boundary
  const RING_R = 110 // centre line of the principle ring
  const RING_W = 7
  const LABEL_R = 121
  const GROUP_R = 130
  const FILL = 0.8 // target share of the boundary area the circles fill
  const RING_GAP_DEG = 2.2
  const GROUP_GAP_DEG = 7

  type Hover =
    | { kind: "node"; id: string }
    | { kind: "principle"; n: number }
    | null

  let hover: Hover = null

  $: nodes_by_id = new Map(data.nodes.map((n) => [n.id, n]))
  $: packed = packWeighted(
    data.nodes.map((n) => ({
      id: n.id,
      weight: n.weight,
      pass: n.kind === "eval" ? 0 : 1,
    })),
    R - 2,
    FILL,
  )
  $: circles = packed.placed
    .map((c) => ({ ...c, node: nodes_by_id.get(c.id) }))
    .filter((c): c is typeof c & { node: CoverageNode } => !!c.node)

  $: principles = data.principles
  $: groups = principleGroups(principles)
  $: has_groups = groups.length > 1 || (groups[0]?.name ?? "") !== ""
  $: VIEW = has_groups ? 160 : 130
  // The labels reach about 140 units out; the box is trimmed below that so
  // the chart wastes no height, and capped to the viewport so the text under
  // it stays on screen.
  $: VIEW_Y = has_groups ? 146 : 130

  function share_of(n: number): number {
    const s = data.shares.get(n)
    if (s !== undefined) return s
    return principles.length > 0 ? 1 / principles.length : 0
  }
  function health_of(n: number): number | null {
    return data.health.get(n) ?? null
  }

  // One arc per principle, as long as its share; a wider gap between groups;
  // a label per group.
  $: ring = (() => {
    const n = principles.length
    if (n === 0) return { arcs: [], labels: [] }
    const group_gaps = has_groups && groups.length > 1 ? groups.length : 0
    const avail = 360 - n * RING_GAP_DEG - group_gaps * GROUP_GAP_DEG
    let angle = -90 + (group_gaps > 0 ? GROUP_GAP_DEG / 2 : 0)
    const arcs: {
      n: number
      text: string
      path: string
      label: { x: number; y: number }
      span: number
      state: "covered" | "planned" | "open"
      health: number | null
    }[] = []
    const labels: {
      name: string
      x: number
      y: number
      anchor: "start" | "middle" | "end"
    }[] = []
    for (const g of groups) {
      const g_start = angle
      for (const p of g.principles) {
        const span = avail * share_of(p.n)
        const a0 = angle + RING_GAP_DEG / 2
        const a1 = a0 + span
        const covered = (data.coverers.get(p.n)?.length ?? 0) > 0
        const planned = (data.planned_for.get(p.n)?.length ?? 0) > 0
        arcs.push({
          n: p.n,
          text: p.text,
          path: arc_path(RING_R, a0, a1),
          label: polar(LABEL_R, (a0 + a1) / 2),
          span,
          state: covered ? "covered" : planned ? "planned" : "open",
          health: health_of(p.n),
        })
        angle = a1 + RING_GAP_DEG / 2
      }
      if (group_gaps > 0 && g.name) {
        const mid = (g_start + angle) / 2
        const pos = polar(GROUP_R, mid)
        const c = Math.cos((mid * Math.PI) / 180)
        labels.push({
          name: g.name,
          x: pos.x,
          y: pos.y,
          anchor: c > 0.35 ? "start" : c < -0.35 ? "end" : "middle",
        })
      }
      if (group_gaps > 0) angle += GROUP_GAP_DEG
    }
    return { arcs, labels }
  })()

  $: hovered_node = hover?.kind === "node" ? nodes_by_id.get(hover.id) : null
  $: hovered_principle_n = hover?.kind === "principle" ? hover.n : null
  $: hovered_principle =
    hovered_principle_n === null
      ? null
      : principles.find((p) => p.n === hovered_principle_n) ?? null
  $: lit_principles = new Set<number>(
    hovered_node
      ? hovered_node.principles
      : hovered_principle
        ? [hovered_principle.n]
        : [],
  )
  $: lit_nodes = new Set<string>(
    hovered_principle
      ? data.nodes
          .filter((n) => n.principles.includes(hovered_principle.n))
          .map((n) => n.id)
      : hovered_node
        ? [hovered_node.id]
        : [],
  )
  $: principle_nodes = hovered_principle
    ? data.nodes.filter(
        (n) => n.kind !== "gap" && n.principles.includes(hovered_principle.n),
      )
    : []
  $: open_count = principles.filter(
    (p) =>
      (data.coverers.get(p.n)?.length ?? 0) === 0 &&
      (data.planned_for.get(p.n)?.length ?? 0) === 0,
  ).length

  // The weight scale, the hard lines and the largest evals, for the summary.
  $: weight_range = (() => {
    const ws = principles
      .map((p) => p.weight)
      .filter((w): w is number => w !== undefined)
    if (ws.length === 0) return null
    return { min: Math.min(...ws), max: Math.max(...ws) }
  })()
  $: top3 = (() => {
    const evals = data.nodes
      .filter((n) => n.kind === "eval")
      .sort((a, b) => b.weight - a.weight)
    const k = Math.min(3, evals.length)
    return { k, share: evals.slice(0, k).reduce((s, n) => s + n.weight, 0) }
  })()

  // Health of what is covered: the importance-weighted mean pass rate.
  $: health_overall = (() => {
    let num = 0
    let den = 0
    for (const p of principles) {
      const h = health_of(p.n)
      if (h === null) continue
      num += share_of(p.n) * h
      den += share_of(p.n)
    }
    return den > 0 ? num / den : null
  })()

  function polar(r: number, deg: number): { x: number; y: number } {
    const a = (deg * Math.PI) / 180
    return { x: r * Math.cos(a), y: r * Math.sin(a) }
  }

  function arc_path(r: number, a0: number, a1: number): string {
    const s = polar(r, a0)
    const e = polar(r, a1)
    const large = a1 - a0 > 180 ? 1 : 0
    return `M ${s.x.toFixed(3)} ${s.y.toFixed(3)} A ${r} ${r} 0 ${large} 1 ${e.x.toFixed(3)} ${e.y.toFixed(3)}`
  }

  // Pass rate as a status: red below 50%, amber below 80%, green from 80%.
  // Pastel tints of the theme's error / warning / success colours for the
  // fill, the full colour for the outline, dark ink for the label.
  const RAG = [
    { max: 0.5, fill: "#F8CAC1", edge: "#E74D31", label: "under 50%" },
    { max: 0.8, fill: "#FBE5BE", edge: "#F4B544", label: "50 to 79%" },
    { max: Infinity, fill: "#B8E6DD", edge: "#33B79D", label: "80% and up" },
  ]
  function rag(rate: number) {
    return RAG.find((s) => rate < s.max) ?? RAG[RAG.length - 1]
  }
  function fill_for(node: CoverageNode): string {
    if (node.kind !== "eval") return node.kind === "gap" ? "#fafafa" : "none"
    if (node.pass_rate === null) return "#f5f5f5"
    return rag(node.pass_rate).fill
  }
  function ink_for(node: CoverageNode): string {
    return node.kind === "planned"
      ? "#415CF5"
      : node.kind === "gap"
        ? "#6b6b6b"
        : "#161616"
  }
  function edge_for(node: CoverageNode): string {
    if (node.kind === "planned") return "#415CF5"
    if (node.kind === "gap" || node.pass_rate === null) return "#bebebe"
    return rag(node.pass_rate).edge
  }
  function arc_stroke(arc: { state: string; health: number | null }): string {
    if (arc.health !== null) return rag(arc.health).fill
    if (arc.state === "covered") return "#aab6f9"
    if (arc.state === "planned") return "#d5dbfb"
    return "#e7e5e4"
  }

  function pct(rate: number | null): string {
    return rate === null ? "—" : `${Math.round(rate * 100)}%`
  }

  /** Word-wraps a label to fit a circle; ends with an ellipsis if cut. */
  function wrap(text: string, max_chars: number, max_lines: number): string[] {
    const words = text.split(/\s+/).filter(Boolean)
    const lines: string[] = []
    let line = ""
    for (const w of words) {
      const next = line ? `${line} ${w}` : w
      if (next.length <= max_chars) {
        line = next
      } else {
        if (line) lines.push(line)
        line = w.length > max_chars ? w.slice(0, max_chars - 1) + "…" : w
        if (lines.length === max_lines) break
      }
    }
    if (lines.length < max_lines && line) lines.push(line)
    if (
      lines.length > max_lines ||
      words.join(" ").length > lines.join(" ").length
    ) {
      lines.splice(max_lines)
      const last = lines[lines.length - 1]
      if (last && !last.endsWith("…")) {
        lines[lines.length - 1] =
          last.slice(0, Math.max(1, max_chars - 1)) + "…"
      }
    }
    return lines
  }

  function label_lines(c: { r: number; node: CoverageNode }): string[] {
    if (c.r < 13) return []
    const max_chars = Math.max(4, Math.floor(c.r / 2.6))
    if (c.r < 24) {
      return c.node.kind === "gap"
        ? [`#${c.node.principles[0] ?? ""}`]
        : c.node.kind === "eval"
          ? [pct(c.node.pass_rate)]
          : wrap(c.node.name, max_chars, 1)
    }
    const name = wrap(c.node.name, max_chars, c.r >= 30 ? 3 : 2)
    if (c.node.kind === "eval") return [...name, pct(c.node.pass_rate)]
    if (c.node.kind === "gap")
      return [`#${c.node.principles[0] ?? ""}`, ...name]
    return [...name, "planned"]
  }

  function node_label(node: CoverageNode): string {
    const share = `${Math.round(node.weight * 100)}% of the product`
    if (node.kind === "gap")
      return `Not covered: ${node.name}. ${share}. Opens the eval builder.`
    if (node.kind === "planned") return `${node.name}, planned eval. ${share}.`
    return `${node.name}, pass rate ${pct(node.pass_rate)}. ${share}.`
  }

  function principle_label(arc: {
    n: number
    text: string
    health: number | null
  }): string {
    return `Principle ${arc.n}: ${arc.text} ${
      arc.health === null
        ? "No eval covers it."
        : `Pass rate ${pct(arc.health)}.`
    }`
  }

  function set_hover(h: Hover) {
    hover = h
  }
  function clear_hover(h: Hover) {
    // Only clear when the leaving element is the one being shown.
    if (!hover || !h) return
    if (hover.kind === "node" && h.kind === "node" && hover.id === h.id) {
      hover = null
    } else if (
      hover.kind === "principle" &&
      h.kind === "principle" &&
      hover.n === h.n
    ) {
      hover = null
    }
  }

  // Pointer tooltip, positioned inside the chart box.
  let chart_box: HTMLDivElement | null = null
  let tip_x = 0
  let tip_y = 0
  let tip_flip = false
  function track(event: MouseEvent) {
    if (!chart_box) return
    const rect = chart_box.getBoundingClientRect()
    tip_x = event.clientX - rect.left
    tip_y = event.clientY - rect.top
    tip_flip = tip_x > rect.width * 0.55
  }
</script>

<div
  class="flex flex-row flex-wrap gap-8 items-start"
  class:opacity-60={loading}
>
  <div class="w-full max-w-[640px] grow shrink basis-[360px] md:basis-[480px]">
    <!-- Legend, above the chart -->
    <div
      class="mb-2 flex flex-row flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500"
    >
      <span
        >Arc length = importance{weight_range
          ? ` (severity × frequency, ${weight_range.min} to ${weight_range.max})`
          : ""} · colour = pass rate:</span
      >
      {#each RAG as step (step.label)}
        <div class="flex items-center gap-1">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <circle cx="6" cy="6" r="5" fill={step.fill} stroke={step.edge} />
          </svg>
          {step.label}
        </div>
      {/each}
      <div class="flex items-center gap-1">
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <circle
            cx="6"
            cy="6"
            r="5"
            fill="none"
            stroke="#415CF5"
            stroke-dasharray="3 2"
          />
        </svg>
        planned eval
      </div>
      <div class="flex items-center gap-1">
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <circle
            cx="6"
            cy="6"
            r="5"
            fill="none"
            stroke="#9ca3af"
            stroke-dasharray="1 2"
          />
        </svg>
        no eval yet
      </div>
    </div>

    <div class="relative" bind:this={chart_box}>
      <svg
        viewBox={`${-VIEW} ${-VIEW_Y} ${2 * VIEW} ${2 * VIEW_Y}`}
        class="mx-auto h-auto max-h-[58vh] w-full select-none"
        role="group"
        aria-label="Eval coverage"
        on:mousemove={track}
        on:mouseleave={() => (hover = null)}
      >
        <!-- The whole product -->
        <circle
          cx="0"
          cy="0"
          r={R}
          fill="#ffffff"
          stroke="#bebebe"
          stroke-width="0.8"
        />

        <!-- The constitution: one arc per principle, as long as its weight,
           grouped by value, tinted by the pass rate of its evals -->
        {#each ring.labels as label (label.name)}
          <text
            x={label.x}
            y={label.y}
            text-anchor={label.anchor}
            dominant-baseline="middle"
            font-size="7.5"
            font-weight="600"
            fill="#6b6b6b"
            pointer-events="none"
          >
            {label.name}
          </text>
        {/each}
        {#each ring.arcs as arc (arc.n)}
          {@const lit = lit_principles.has(arc.n)}
          {@const dim = hover !== null && !lit}
          <g
            class="cursor-default"
            role="button"
            tabindex="0"
            aria-label={principle_label(arc)}
            on:mouseenter={() => set_hover({ kind: "principle", n: arc.n })}
            on:mouseleave={() => clear_hover({ kind: "principle", n: arc.n })}
            on:focus={() => set_hover({ kind: "principle", n: arc.n })}
            on:blur={() => clear_hover({ kind: "principle", n: arc.n })}
          >
            <!-- wide invisible hit target -->
            <path
              d={arc.path}
              fill="none"
              stroke="transparent"
              stroke-width={RING_W + 12}
            />
            <path
              d={arc.path}
              fill="none"
              stroke={lit ? "#415CF5" : arc_stroke(arc)}
              stroke-width={lit ? RING_W + 2 : RING_W}
              opacity={dim ? 0.55 : 1}
              class="transition-all duration-150"
            />
            {#if principles.length <= 30 && arc.span >= 4}
              <text
                x={arc.label.x}
                y={arc.label.y}
                text-anchor="middle"
                dominant-baseline="middle"
                font-size="6.5"
                fill={lit ? "#161616" : "#6b6b6b"}
                font-weight={lit ? "600" : "400"}
              >
                {arc.n}
              </text>
            {/if}
          </g>
        {/each}

        <!-- The evals -->
        {#each circles as c (c.id)}
          {@const lit = lit_nodes.has(c.id)}
          {@const dim = hover !== null && !lit}
          <svelte:element
            this={c.node.href ? "a" : "g"}
            href={c.node.href ?? undefined}
            role={c.node.href ? undefined : "img"}
            aria-label={node_label(c.node)}
            class={c.node.href ? "cursor-pointer" : "cursor-default"}
            on:mouseenter={() => set_hover({ kind: "node", id: c.id })}
            on:mouseleave={() => clear_hover({ kind: "node", id: c.id })}
            on:focus={() => set_hover({ kind: "node", id: c.id })}
            on:blur={() => clear_hover({ kind: "node", id: c.id })}
          >
            <circle
              cx={c.x}
              cy={c.y}
              r={c.r}
              fill={fill_for(c.node)}
              stroke={lit ? "#131517" : edge_for(c.node)}
              stroke-width={lit
                ? 1.8
                : data.floor && c.id === data.floor.id
                  ? 2.6
                  : 1.2}
              stroke-dasharray={c.node.kind === "planned"
                ? "3 2"
                : c.node.kind === "gap"
                  ? "1 2"
                  : undefined}
              opacity={dim ? 0.55 : 1}
              class="transition-opacity duration-150"
            />
            {#if label_lines(c).length > 0}
              {@const lines = label_lines(c)}
              {@const is_rate = c.node.kind === "eval"}
              {@const size = c.r >= 24 ? 6.2 : 7}
              {@const start = c.y - ((lines.length - 1) * size * 1.25) / 2}
              <text
                text-anchor="middle"
                font-size={size}
                fill={ink_for(c.node)}
                opacity={dim ? 0.8 : 1}
                pointer-events="none"
              >
                {#each lines as line, i}
                  <tspan
                    x={c.x}
                    y={start + i * size * 1.25}
                    dominant-baseline="middle"
                    font-weight={is_rate && i === lines.length - 1
                      ? "700"
                      : "500"}
                    font-size={is_rate &&
                    i === lines.length - 1 &&
                    lines.length > 1
                      ? size * 1.15
                      : size}
                  >
                    {line}
                  </tspan>
                {/each}
              </text>
            {/if}
          </svelte:element>
        {/each}
      </svg>
      {#if hovered_node || hovered_principle}
        <div
          class="pointer-events-none absolute z-10 w-max max-w-[260px] rounded-md border bg-base-100 px-2 py-1 text-xs shadow-md"
          style={`left:${tip_x}px; top:${tip_y}px; transform: translate(${tip_flip ? "calc(-100% - 12px)" : "12px"}, 12px);`}
          role="tooltip"
        >
          {#if hovered_node}
            {#if hovered_node.kind === "gap"}
              <span class="font-medium"
                >Principle {hovered_node.principles[0]}</span
              >
              <span class="text-gray-500">· not covered</span>
            {:else}
              <span class="font-medium">{hovered_node.name}</span>
              {#if hovered_node.kind === "eval"}
                <span class="text-gray-500"
                  >· {pct(hovered_node.pass_rate)}{hovered_node.dataset_size !==
                  null
                    ? ` of ${hovered_node.dataset_size}`
                    : ""}</span
                >
              {:else}
                <span class="text-gray-500">· planned</span>
              {/if}
            {/if}
          {:else if hovered_principle}
            <span class="font-medium">Principle {hovered_principle.n}</span>
            {#if hovered_principle.group}
              <span class="text-gray-500">· {hovered_principle.group}</span>
            {/if}
            <span class="text-gray-500"
              >· {pct(health_of(hovered_principle.n))}</span
            >
          {/if}
        </div>
      {/if}
    </div>

    <!-- What is under the pointer, below the chart -->
    <div class="mt-2 text-sm min-h-[6rem]" aria-live="polite">
      {#if hovered_node}
        <div class="font-medium">{hovered_node.name}</div>
        <div class="text-gray-500 mt-1">
          {#if hovered_node.kind === "gap"}
            No eval tests this principle yet. Click the circle to create one in
            the eval builder.
          {:else if hovered_node.kind === "planned"}
            Planned eval, not yet active.
          {:else}
            Pass rate <span class="font-medium"
              >{pct(hovered_node.pass_rate)}</span
            >
            {#if hovered_node.dataset_size !== null}
              on {hovered_node.dataset_size} test cases
            {/if}
            {#if hovered_node.pass_rate === null}
              (no results on this run config)
            {/if}
          {/if}
          · tests {Math.round(hovered_node.weight * 100)}% of the constitution
          {#if hovered_node.priority !== null}
            · {formatPriority(hovered_node.priority)}
          {/if}
        </div>
        {#if hovered_node.kind !== "gap" && principles.length > 0}
          <div class="mt-1 text-gray-500">
            {#if hovered_node.principles.length === 0}
              No principles tagged. Tag the eval with
              <code class="text-xs">principle_&lt;n&gt;</code> to count it.
            {:else}
              Principles {hovered_node.principles.join(", ")}
            {/if}
          </div>
        {/if}
      {:else if hovered_principle}
        <div class="font-medium">
          Principle {hovered_principle.n}
          {#if hovered_principle.group}
            <span class="font-normal text-gray-500"
              >· {hovered_principle.group}</span
            >
          {/if}
          {#if hovered_principle.weight !== undefined}
            <span class="font-normal text-gray-500"
              >· importance {Math.round(share_of(hovered_principle.n) * 100)}%
              (weight {hovered_principle.weight}{hovered_principle.weight_note
                ? `: ${hovered_principle.weight_note}`
                : ""})</span
            >
          {/if}
        </div>
        <div class="mt-1">{hovered_principle.text}</div>
        {#if hovered_principle.fails_when}
          <div class="mt-1 text-gray-500">
            Fails when {hovered_principle.fails_when}
          </div>
        {/if}
        <div class="mt-1 text-gray-500">
          {#if principle_nodes.length === 0}
            No eval covers this principle.
          {:else}
            Pass rate {pct(health_of(hovered_principle.n))} from {principle_nodes
              .map((n) => n.name)
              .join(", ")}
          {/if}
        </div>
      {:else}
        <div class="text-gray-500">
          Hover an arc for the principle, or a circle for the eval. Click a
          circle to open the eval, or to create one where there is none.
        </div>
      {/if}
    </div>
  </div>

  <div class="flex-1 min-w-[240px] flex flex-col gap-4">
    <SettingsHeader title="Coverage" show_divider={false} />
    <slot name="controls" />

    {#if data.covered !== null}
      <div class="flex flex-col gap-3">
        <div>
          <div class="text-2xl font-medium">
            {Math.round(data.covered * 100)}%
          </div>
          <div class="text-sm">Covered</div>
          <div class="text-sm text-gray-500">
            How much of the constitution has an eval, weighted by how much each
            principle matters.
          </div>
        </div>
        {#if health_overall !== null}
          <div>
            <div class="text-2xl font-medium">{pct(health_overall)}</div>
            <div class="text-sm">Passing</div>
            <div class="text-sm text-gray-500">
              The pass rate across the covered principles, weighted the same
              way.
            </div>
          </div>
        {/if}
        {#if data.floor}
          <div>
            <div class="text-2xl font-medium">{pct(data.floor.pass_rate)}</div>
            <div class="text-sm">Weakest eval</div>
            <div class="text-sm text-gray-500">{data.floor.name}</div>
          </div>
        {/if}
      </div>
      <div class="text-sm text-gray-500">
        The ring is the constitution, one arc per principle: length is
        importance (severity × frequency, set in the constitution), colour is
        the pass rate of the evals that test it. Circles are evals, sized by how
        much of the constitution they test. Dotted circles have no eval yet. The {top3.k}
        largest evals test {Math.round(top3.share * 100)}% of the constitution; {principles.length -
          open_count} of {principles.length}
        principles have an eval.
      </div>
    {:else}
      <div>
        <div class="text-2xl font-medium">{data.active_count}</div>
        <div class="text-sm text-gray-500">
          active {data.active_count === 1 ? "eval" : "evals"}, sized by
          priority. Add a numbered list of principles to the task description to
          measure coverage.
        </div>
      </div>
    {/if}
  </div>
</div>

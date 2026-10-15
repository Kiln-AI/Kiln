<script lang="ts">
  import type {
    CoverageData,
    CoverageNode,
  } from "$lib/utils/eval_coverage/eval_coverage_data"
  import { packWeighted } from "$lib/utils/eval_coverage/circle_pack"
  import { formatPriority } from "$lib/utils/formatters"

  /**
   * Eval coverage chart.
   *
   * One large circle is the whole product. Inside it, one circle per eval,
   * packed tightly: area is the share of the constitution the eval holds,
   * fill is its pass rate. Dashed circles are planned evals; dotted circles
   * are principles with no eval. The ring around the outside has one arc
   * per principle of the constitution; hovering links the two.
   */

  export let data: CoverageData
  /** True while pass rates are loading: the chart holds at reduced opacity. */
  export let loading = false

  // Geometry in viewBox units.
  const R = 100 // packing boundary
  const RING_R = 110 // centre line of the principle ring
  const RING_W = 7
  const LABEL_R = 121
  const VIEW = 130
  const FILL = 0.8 // target share of the boundary area the circles fill
  const RING_GAP_DEG = 2.5

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
  $: arcs = principles.map((p, i) => {
    const span = 360 / principles.length
    const a0 = -90 + i * span + RING_GAP_DEG / 2
    const a1 = a0 + span - RING_GAP_DEG
    const covered = (data.coverers.get(p.n)?.length ?? 0) > 0
    const planned = (data.planned_for.get(p.n)?.length ?? 0) > 0
    return {
      n: p.n,
      text: p.text,
      path: arc_path(RING_R, a0, a1),
      label: polar(LABEL_R, (a0 + a1) / 2),
      state: covered ? "covered" : planned ? "planned" : "open",
    }
  })

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
  $: open_principles = principles.filter(
    (p) =>
      (data.coverers.get(p.n)?.length ?? 0) === 0 &&
      (data.planned_for.get(p.n)?.length ?? 0) === 0,
  )

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

  // Sequential fill for pass rate: one hue, light to dark, five steps.
  const RATE_STEPS = ["#e4e8fd", "#bcc6fb", "#8e9ff8", "#5c74f0", "#2a3fc2"]
  function rate_step(rate: number): number {
    return Math.min(RATE_STEPS.length - 1, Math.floor(rate * RATE_STEPS.length))
  }
  function fill_for(node: CoverageNode): string {
    if (node.kind !== "eval") return node.kind === "gap" ? "#fafafa" : "none"
    if (node.pass_rate === null) return "#f5f5f5"
    return RATE_STEPS[rate_step(node.pass_rate)]
  }
  function ink_for(node: CoverageNode): string {
    if (node.kind === "eval" && node.pass_rate !== null) {
      return rate_step(node.pass_rate) >= 3 ? "#ffffff" : "#161616"
    }
    return node.kind === "planned" ? "#415CF5" : "#6b6b6b"
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
    const name = wrap(c.node.name, max_chars, 2)
    if (c.node.kind === "eval") return [...name, pct(c.node.pass_rate)]
    if (c.node.kind === "gap")
      return [`#${c.node.principles[0] ?? ""}`, ...name]
    return [...name, "planned"]
  }

  function node_label(node: CoverageNode): string {
    const share = `${Math.round(node.weight * 100)}% of the product`
    if (node.kind === "gap") return `Not covered: ${node.name}. ${share}.`
    if (node.kind === "planned") return `${node.name}, planned eval. ${share}.`
    return `${node.name}, pass rate ${pct(node.pass_rate)}. ${share}.`
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
</script>

<div
  class="flex flex-row flex-wrap gap-8 items-start"
  class:opacity-60={loading}
>
  <div
    class="w-full max-w-[440px] grow-0 shrink-0 basis-[320px] sm:basis-[400px]"
  >
    <svg
      viewBox={`${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`}
      class="w-full h-auto select-none"
      role="group"
      aria-label="Eval coverage"
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

      <!-- The constitution: one arc per principle -->
      {#each arcs as arc (arc.n)}
        <g
          class="cursor-default"
          role="button"
          tabindex="0"
          aria-label={`Principle ${arc.n}: ${arc.text}`}
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
            stroke-width={RING_W + 10}
          />
          <path
            d={arc.path}
            fill="none"
            stroke={lit_principles.has(arc.n)
              ? "#415CF5"
              : arc.state === "covered"
                ? "#aab6f9"
                : arc.state === "planned"
                  ? "#d5dbfb"
                  : "#e7e5e4"}
            stroke-width={lit_principles.has(arc.n) ? RING_W + 2 : RING_W}
            opacity={hover && !lit_principles.has(arc.n) ? 0.55 : 1}
            class="transition-all duration-150"
          />
          {#if principles.length <= 24}
            <text
              x={arc.label.x}
              y={arc.label.y}
              text-anchor="middle"
              dominant-baseline="middle"
              font-size="6.5"
              fill={lit_principles.has(arc.n) ? "#161616" : "#6b6b6b"}
              font-weight={lit_principles.has(arc.n) ? "600" : "400"}
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
            stroke={lit
              ? "#131517"
              : c.node.kind === "planned"
                ? "#415CF5"
                : c.node.kind === "gap"
                  ? "#bebebe"
                  : c.node.pass_rate === null
                    ? "#bebebe"
                    : rate_step(c.node.pass_rate) >= 2
                      ? "#ffffff"
                      : "#b3bdf5"}
            stroke-width={lit ? 1.6 : 1}
            stroke-dasharray={c.node.kind === "planned"
              ? "3 2"
              : c.node.kind === "gap"
                ? "1 2"
                : undefined}
            opacity={dim ? 0.45 : 1}
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
              opacity={dim ? 0.45 : 1}
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
  </div>

  <div class="flex-1 min-w-[240px] flex flex-col gap-4">
    <div class="flex flex-row flex-wrap items-center justify-between gap-2">
      <div class="text-xl font-bold">Coverage</div>
      <slot name="controls" />
    </div>

    {#if data.covered !== null}
      <div>
        <div class="text-4xl font-medium">
          {Math.round(data.covered * 100)}%
        </div>
        <div class="text-sm text-gray-500">
          {principles.length - open_principles.length} of {principles.length}
          principles have an active or planned eval. {data.active_count} active
          {data.active_count === 1 ? "eval" : "evals"}.
        </div>
      </div>
    {:else}
      <div>
        <div class="text-4xl font-medium">{data.active_count}</div>
        <div class="text-sm text-gray-500">
          active {data.active_count === 1 ? "eval" : "evals"}, sized by
          priority. Add a numbered list of principles to the task description to
          measure coverage.
        </div>
      </div>
    {/if}

    <div class="rounded-lg border p-4 text-sm min-h-[7rem]" aria-live="polite">
      {#if hovered_node}
        <div class="font-medium">{hovered_node.name}</div>
        <div class="text-gray-500 mt-1">
          {#if hovered_node.kind === "gap"}
            No eval covers this principle.
          {:else if hovered_node.kind === "planned"}
            Planned eval, not yet active.
          {:else}
            Pass rate <span class="font-medium text-gray-800"
              >{pct(hovered_node.pass_rate)}</span
            >
            {#if hovered_node.dataset_size !== null}
              on {hovered_node.dataset_size} test cases
            {/if}
            {#if hovered_node.pass_rate === null}
              (no results on this run config)
            {/if}
          {/if}
          · {Math.round(hovered_node.weight * 100)}% of the product
          {#if hovered_node.priority !== null}
            · {formatPriority(hovered_node.priority)}
          {/if}
        </div>
        {#if hovered_node.kind !== "gap" && principles.length > 0}
          <div class="mt-2 text-gray-500">
            {#if hovered_node.principles.length === 0}
              No principles tagged. Tag the eval with
              <code class="text-xs">principle_&lt;n&gt;</code> to count it.
            {:else}
              Principles {hovered_node.principles.join(", ")}
            {/if}
          </div>
        {/if}
        {#if hovered_node.href}
          <div class="mt-2 text-xs text-gray-400">Click to open</div>
        {/if}
      {:else if hovered_principle}
        <div class="font-medium">Principle {hovered_principle.n}</div>
        <div class="text-gray-700 mt-1">{hovered_principle.text}</div>
        <div class="mt-2 text-gray-500">
          {#if principle_nodes.length === 0}
            No eval covers this principle.
          {:else}
            Covered by {principle_nodes.map((n) => n.name).join(", ")}
          {/if}
        </div>
      {:else}
        <div class="text-gray-500">
          Hover a circle or an arc for details. Click a circle to open the eval.
        </div>
        <div
          class="mt-3 flex flex-row flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500"
        >
          <div class="flex items-center gap-1">
            <span>Pass rate</span>
            {#each RATE_STEPS as step}
              <span
                class="inline-block h-3 w-3 rounded-full"
                style={`background:${step}`}
              ></span>
            {/each}
            <span>0–100%</span>
          </div>
          <div class="flex items-center gap-1">
            <span
              class="inline-block h-3 w-3 rounded-full border border-dashed border-primary"
            ></span>
            planned
          </div>
          <div class="flex items-center gap-1">
            <span
              class="inline-block h-3 w-3 rounded-full border border-dotted border-gray-400"
            ></span>
            not covered
          </div>
        </div>
      {/if}
    </div>

    {#if open_principles.length > 0}
      <div class="text-sm">
        <div class="text-gray-500 mb-1">Principles with no eval</div>
        <div class="flex flex-row flex-wrap gap-1">
          {#each open_principles as p (p.n)}
            <button
              type="button"
              class="badge badge-outline badge-sm cursor-default"
              class:badge-primary={lit_principles.has(p.n)}
              on:mouseenter={() => set_hover({ kind: "principle", n: p.n })}
              on:mouseleave={() => clear_hover({ kind: "principle", n: p.n })}
              on:focus={() => set_hover({ kind: "principle", n: p.n })}
              on:blur={() => clear_hover({ kind: "principle", n: p.n })}
            >
              {p.n}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</div>

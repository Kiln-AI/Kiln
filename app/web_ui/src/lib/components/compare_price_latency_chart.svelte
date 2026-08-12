<script lang="ts">
  // Price against latency, with quality held to a floor: the chart that answers
  // "which of these do we ship".
  //
  // Everything else on this page compares run configs one quantity at a time,
  // which is the right shape for a question about quality - a pass rate is
  // better or worse and nothing else. Shipping is not that question. It is a
  // trade between two costs that are both real and are not interchangeable
  // (money, and how long a user waits), asked only of the configs that are good
  // enough to be candidates at all. That is a scatter with a gate, and it is the
  // one view here where the answer is a SET - the frontier - rather than a
  // winner.
  //
  // Why quality is a gate and not a third encoding. Size or colour would put
  // quality on the same picture as price and invite trading them off against
  // each other by eye, and there is no exchange rate between a point of pass
  // rate and a cent: nobody can say what 2% more quality is worth in dollars,
  // and a chart that implies they can is worse than one that refuses. A floor is
  // a decision the READER states, and above it price and speed are comparable on
  // their own.
  //
  // Configs below the floor stay, ghosted. The cheap arm is usually cheap
  // BECAUSE it is bad, and that is the most useful thing on the chart: dropping
  // it silently would leave a reader wondering where the cheap option went, and
  // plotting it solid would put an unshippable config on the frontier.
  //
  // Log cost, linear seconds. The arms on a real task span roughly two orders of
  // magnitude of cost (a mini lane against a reasoning lane is ~27x) and well
  // under one of latency; on a linear cost axis every cheap config collapses
  // onto the floor and the chart says only "one of these is expensive". Log
  // gives the cheap end its own room, and ratio - "twice the price" - is the
  // comparison actually made about cost anyway.
  //
  // The geometry and the gate arithmetic are in $lib/utils/evolution/price_latency,
  // tested there; this file is drawing.

  import * as echarts from "echarts"
  import type { TaskRunConfig, ProviderModels } from "$lib/types"
  import {
    FALLBACK_SERIES_COLOR,
    series_label,
  } from "$lib/utils/evolution/series_identity"
  import {
    build_price_latency_points,
    format_cost_tick,
    latency_seconds,
    pareto_frontier,
    split_by_gate,
    GHOST_LABELS,
    MIN_PRICE_LATENCY_POINTS,
    OMISSION_LABELS,
    type GhostReason,
    type PricePoint,
  } from "$lib/utils/evolution/price_latency"
  import { COST_KEY } from "$lib/utils/evolution/metric_axes"
  import {
    below_gate_reason,
    quality_tooltip_lines,
    type QualityBreakdown,
  } from "$lib/utils/evolution/quality_score"
  import { formatLatency } from "$lib/utils/formatters"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  export let run_configs: TaskRunConfig[] = []
  // Only for the name fallback when a config has no name of its own
  export let model_info: ProviderModels | null = null
  // Only what the page's legend has left switched on. This chart draws no
  // legend of its own - see evolution_legend.svelte - so a hidden config never
  // arrives rather than arriving and being suppressed here.
  export let selectedRunConfigIds: string[] = []
  // Colour per run config id, fixed by the page (series_color_map) rather than
  // by this chart's series order, so a config is the same colour on all four
  // plots. Empty falls back to the theme palette by index.
  export let seriesColors: Record<string, string> = {}
  // What to CALL each run config, by id, decided once by the page for the
  // whole comparison - see series_display_map, which leads with the model and
  // appends the config's name only where a model is shared. These names are
  // drawn ON the chart beside each dot, which is exactly the single-line
  // context that dedup rule exists for: two dots called "GPT-5.4-mini" would
  // be two configs the reader cannot tell apart. Empty falls back to
  // series_label.
  export let seriesLabels: Record<string, string> = {}
  // Both axes come from the usage rollup, under the same keys the metrics chart
  // uses. Passed in rather than read here so this chart is scoped by whatever
  // split the page is showing, like every other card on it.
  export let getMetricValue: (runConfigId: string, key: string) => number | null
  // Direction-corrected quality, 0..1, or null for a config with no scores.
  // What the gate is applied to.
  export let getQuality: (runConfigId: string) => number | null
  // What that number is MADE of: the concern areas, their values, and the axes
  // under the weakest one. Optional, with the old single-line tooltip as the
  // fallback - a scalar gate needs no breakdown to work, but a reader asking
  // "why is this one below the line" is asking about the breakdown, and a
  // chart that can only answer "74%" is asking them to go and find out
  // elsewhere.
  export let getQualityBreakdown: (
    runConfigId: string,
  ) => QualityBreakdown | null = () => null
  // Runs behind the cost mean, when the page knows it. Usually null: the usage
  // rollup arrives as a blob of means with no count attached, unlike an eval
  // score. Asked for anyway, so the tooltip states n the moment there is one to
  // state rather than needing this chart changed.
  export let getSampleSize: (
    runConfigId: string,
    key: string,
  ) => number | null = () => null
  // The quality floor, 0..1, or null for "no gate". Owned by the page - it is
  // round-tripped through the URL, so a shared link carries the reader's
  // decision with it.
  export let qualityFloor: number | null = null
  // Which slice of the dataset these numbers are over. Always stated on this
  // card, even for the default split: cost per conversation on a 25-item train
  // split is a different claim from cost on the test set, and this is the card
  // someone screenshots to argue for a config.
  export let scopeLabel: string | null = null

  // Reactive, because what the gate MEANS depends on whether the task grouped
  // its criteria: with families the floor is non-compensatory, and that is the
  // sentence a reader has to have before they set one.
  $: SCALE_TOOLTIP = `One dot per run config: how long a conversation takes against what it costs. **Down and to the left is better** on both.

**Cost is on a log scale.** The arms on a real task span a couple of orders of magnitude, and on a linear axis every cheap one collapses onto the floor. Each gridline is a fixed RATIO, not a fixed amount.

**The quality gate** is yours to set. ${
    qualityIsGrouped
      ? "It holds EVERY concern area to the floor, not the average of them — so a config cannot clear it by doing well on the criteria nobody was worried about. Hover a dot for its weakest area."
      : "It is the mean of every criterion on the task."
  } Configs that clear it are solid and joined by the dashed **frontier** — the ones nothing else beats on both price and speed. A config above that line is paying for nothing: something on it is cheaper AND faster.

Configs below the gate stay on the chart, hollow, because "the cheap one is cheap because it is bad" is worth seeing.

Latency is LLM generation time only. Tool execution, retrieval and network time are not in it.`

  // The caveat is the chart's, not the page's: whoever reads these axes has to
  // know what the x one leaves out, wherever the card ends up.
  const LATENCY_CAVEAT =
    "Latency is LLM generation time only (excludes tool execution)."

  const AXIS_LABEL_COLOR = "#9ca3af"
  const AXIS_NAME_COLOR = "#6b7280"
  const GRID_LINE_COLOR = "#f3f4f6"
  // The frontier is a property of the SET, so it takes no config's colour. Grey
  // and dashed: a construction line, not a series.
  const FRONTIER_COLOR = "#9ca3af"
  const POINT_SIZE = 15
  const GHOST_POINT_SIZE = 12
  // A ghost is legible but never mistaken for a candidate
  const GHOST_OPACITY = 0.5
  // Names are drawn beside the dots, so they need a cap: a config called "Nova
  // GPT5p4 OR v7 write-routing" is wider than the plot can spare.
  const LABEL_MAX_WIDTH = 132

  let chartInstance: echarts.ECharts | null = null

  function displayName(runConfigId: string): string {
    const assigned = seriesLabels[runConfigId]
    if (assigned) return assigned
    const config = run_configs.find((candidate) => candidate.id === runConfigId)
    return config ? series_label(config, model_info) : "Unknown"
  }

  // The page is the authority on what colour a run config is - see
  // series_color_map. The palette read is the fallback for a caller that
  // supplies none.
  function colorFor(runConfigId: string, index: number): string {
    const assigned = seriesColors[runConfigId]
    if (assigned) return assigned
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return FALLBACK_SERIES_COLOR
    return palette[index % palette.length]
  }

  // Only the configs the legend has left on, and only the ones with both
  // numbers. `omitted` is what the footnote names.
  $: built = build_price_latency_points(
    selectedRunConfigIds,
    getMetricValue,
    getQuality,
  )
  $: gated = split_by_gate(built.plotted, qualityFloor)
  $: frontier = pareto_frontier(gated.qualifying)

  // Two points make a trade-off; one makes a dot. The floor is on the PLOTTED
  // set rather than the qualifying one, because a gate that nothing clears is a
  // finding - the chart should show the reader their floor is above everything
  // they have, not go blank and look broken.
  $: hasData = built.plotted.length >= MIN_PRICE_LATENCY_POINTS

  // Colour is keyed by position in the pinned list, which is the order this
  // chart receives, so the index fallback lines up with the other charts'.
  $: colorIndex = new Map(
    selectedRunConfigIds.map((id, index) => [id, index] as const),
  )

  $: floorPercent =
    qualityFloor === null ? null : Math.round(qualityFloor * 100)

  // Whether the task grouped its criteria, read off the points themselves
  // rather than passed in: the breakdown is already here, and a second prop
  // saying the same thing could disagree with it.
  $: qualityIsGrouped = built.plotted.some(
    (point) => getQualityBreakdown(point.id)?.mode === "families",
  )

  $: subtitle = (() => {
    const parts = [
      "Cost against speed for the selected run configurations, one dot each.",
    ]
    if (scopeLabel) parts.push(`${scopeLabel} only.`)
    if (floorPercent === null) {
      parts.push("Set a quality gate to hold quality fixed and compare price.")
    } else {
      parts.push(
        `Quality gate ${
          qualityIsGrouped
            ? `every area ≥ ${floorPercent}%`
            : `${floorPercent}%`
        }: ${gated.qualifying.length} of ${built.plotted.length} clear it, joined by the frontier. The rest are hollow.`,
      )
    }
    return parts.join(" ")
  })()

  // What is not on the chart, and why - the same rule the radar states. A
  // config with no cost is not a free one, and the server only reports a rollup
  // field when at least half the runs recorded it, so a missing number means
  // "not measured often enough" rather than "zero".
  $: omissionNote =
    built.omitted.length === 0
      ? null
      : `Not plotted: ${built.omitted
          .map(
            (entry) =>
              `${displayName(entry.id)} (${OMISSION_LABELS[entry.reason]})`,
          )
          .join(", ")}.`

  function formatQuality(quality: number | null): string {
    if (quality === null) return "not scored"
    return `${(quality * 100).toFixed(0)}%`
  }

  function tooltipMarker(color: string, hollow: boolean): string {
    const fill = hollow ? "transparent" : color
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${fill};border:2px solid ${color};box-sizing:border-box;margin-right:6px;"></span>`
  }

  interface PlotDatum {
    /** [seconds, usd] - what the axes are drawn in */
    value: [number, number]
    id: string
    name: string
    cost: number
    latency_ms: number
    quality: number | null
    ghost: GhostReason | null
    itemStyle: Record<string, unknown>
  }

  function datumFor(point: PricePoint, ghost: GhostReason | null): PlotDatum {
    const color = colorFor(point.id, colorIndex.get(point.id) ?? 0)
    return {
      value: [latency_seconds(point.latency_ms), point.cost],
      id: point.id,
      name: displayName(point.id),
      cost: point.cost,
      latency_ms: point.latency_ms,
      quality: point.quality,
      ghost,
      itemStyle: ghost
        ? {
            // Hollow: the ring says "this config exists and is not a
            // candidate", which a faded disc does not - a faded disc just reads
            // as a disc drawn badly.
            color: "transparent",
            borderColor: color,
            borderWidth: 2,
            opacity: GHOST_OPACITY,
          }
        : { color, borderColor: "#fff", borderWidth: 1.5 },
    }
  }

  function escape_html(text: string): string {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
  }

  function itemTooltip(datum: PlotDatum): string {
    const color = colorFor(datum.id, colorIndex.get(datum.id) ?? 0)
    const n = getSampleSize(datum.id, COST_KEY)
    const breakdown = getQualityBreakdown(datum.id)
    let html = `<div style="font-weight:bold;">${tooltipMarker(
      color,
      datum.ghost !== null,
    )}${datum.name}</div>`
    html += `<div style="margin-top:4px;">Cost: <b>$${datum.cost.toFixed(4)}</b> <span style="color:#888;">per conversation</span></div>`
    html += `<div>Model time: <b>${formatLatency(datum.latency_ms)}</b> <span style="color:#888;">per conversation</span></div>`
    // The breakdown's own first line already says what the number is and which
    // area it came from, so it replaces the plain "Quality: 74%" rather than
    // sitting under it.
    const quality_lines = quality_tooltip_lines(breakdown, qualityFloor)
    if (quality_lines.length > 0) {
      html += `<div style="margin-top:4px;">${escape_html(quality_lines[0])}</div>`
      for (const line of quality_lines.slice(1)) {
        html += `<div style="color:#888;">${escape_html(line)}</div>`
      }
    } else {
      html += `<div>Quality: <b>${formatQuality(datum.quality)}</b></div>`
    }
    if (n !== null) {
      html += `<div style="color:#888;">n=${n}</div>`
    }
    if (datum.ghost) {
      // The area that failed, when the page knows it: "below the gate" says a
      // config lost without saying what it lost on, and the reader's next
      // question is always which one.
      const reason =
        (datum.ghost === "below_gate"
          ? below_gate_reason(breakdown, qualityFloor)
          : null) ?? GHOST_LABELS[datum.ghost]
      html += `<div style="margin-top:4px;color:#888;">${escape_html(reason)}</div>`
    } else if (frontier.some((point) => point.id === datum.id)) {
      html += `<div style="margin-top:4px;color:#888;">On the frontier — nothing here is both cheaper and faster.</div>`
    }
    return html
  }

  function buildSeries(): echarts.SeriesOption[] {
    // Candidates FIRST, and that order is load-bearing: hideOverlap places
    // labels in the order the series are declared and drops whichever one
    // arrives on top of an already-placed name, so declaring the gated-out
    // configs first would let a ghost's name suppress a candidate's. Draw order
    // is set by `z` instead, so it stays independent of this.
    const series: echarts.SeriesOption[] = [
      {
        name: "Run configs",
        type: "scatter",
        symbolSize: POINT_SIZE,
        data: gated.qualifying.map((point) => datumFor(point, null)),
        label: {
          show: true,
          position: "top",
          distance: 8,
          fontSize: 11,
          color: "#374151",
          width: LABEL_MAX_WIDTH,
          overflow: "truncate",
          formatter: (params: { data?: unknown }) =>
            (params.data as PlotDatum | undefined)?.name ?? "",
        },
        // Names beside dots overlap the moment two configs are close, and an
        // overlapped pair is two unreadable names instead of one readable one.
        // Dropping the loser is right here because nothing is lost with it: the
        // dot stays, the colour keys it to the legend above, and the tooltip
        // names it.
        labelLayout: { hideOverlap: true },
        z: 4,
      },
      {
        name: "Below the gate",
        type: "scatter",
        symbolSize: GHOST_POINT_SIZE,
        data: gated.ghosted.map((point) => datumFor(point, point.reason)),
        label: {
          show: true,
          position: "top",
          distance: 7,
          fontSize: 10,
          // Muted to match the mark: named, because "which arm is the cheap bad
          // one" is a question the chart is read to answer.
          color: "#9ca3af",
          width: LABEL_MAX_WIDTH,
          overflow: "truncate",
          formatter: (params: { data?: unknown }) =>
            (params.data as PlotDatum | undefined)?.name ?? "",
        },
        labelLayout: { hideOverlap: true },
        z: 3,
      },
    ]

    // One point is its own frontier and needs no line drawn through it.
    if (frontier.length >= 2) {
      series.push({
        name: "Frontier",
        type: "line",
        // A staircase, not a straight line between the dots: the frontier is
        // "the least this can cost at or under this much time", which holds
        // flat until the next config that beats it. A diagonal would draw a
        // continuum of configs that do not exist.
        step: "end",
        symbol: "none",
        silent: true,
        tooltip: { show: false },
        lineStyle: { color: FRONTIER_COLOR, width: 1.5, type: "dashed" },
        data: frontier.map((point) => [
          latency_seconds(point.latency_ms),
          point.cost,
        ]),
        z: 1,
      })
    }

    return series
  }

  function updateChart() {
    if (!chartInstance) return
    if (!hasData) {
      chartInstance.clear()
      return
    }

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          confine: true,
          borderWidth: 0,
          textStyle: { fontSize: 12 },
          formatter: (params: unknown) => {
            const datum = (params as { data?: PlotDatum }).data
            return datum ? itemTooltip(datum) : ""
          },
        },
        // No legend of its own: there is ONE legend for this whole section,
        // above the charts (evolution_legend.svelte).
        legend: { show: false },
        grid: {
          left: 16,
          // Room for the rightmost dot's name, which is centred over it and so
          // hangs half its width past the plot
          right: 72,
          top: 24,
          bottom: 8,
          containLabel: true,
        },
        xAxis: {
          type: "value",
          name: "Model time per conversation (s)",
          nameLocation: "middle",
          nameGap: 32,
          nameTextStyle: { color: AXIS_NAME_COLOR, fontSize: 11 },
          // Fitted to the configs shown rather than anchored at zero. Every
          // config here answers the same prompts, so the interesting quantity is
          // the spread between them; a zero-anchored axis would squeeze four
          // configs that differ by 2x into the last inch of the plot.
          scale: true,
          axisLabel: {
            color: AXIS_LABEL_COLOR,
            fontSize: 11,
            formatter: (value: number) =>
              `${value >= 10 ? Math.round(value) : value}s`,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
        },
        yAxis: {
          type: "log",
          logBase: 10,
          name: "Cost per conversation (USD)",
          nameLocation: "middle",
          nameGap: 58,
          nameTextStyle: { color: AXIS_NAME_COLOR, fontSize: 11 },
          axisLabel: {
            color: AXIS_LABEL_COLOR,
            fontSize: 11,
            formatter: format_cost_tick,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: { lineStyle: { color: GRID_LINE_COLOR } },
        },
        series: buildSeries(),
      },
      true,
    )
  }

  // Redraw when anything that changes the picture changes. The getters are
  // referenced rather than tested: they are always defined, but referencing
  // them is what makes a rebuilt one (the page rebuilds its metric getter when
  // the lazily fetched usage arrives) count as a dependency.
  $: redraw(
    chartInstance,
    built,
    gated,
    frontier,
    hasData,
    selectedRunConfigIds,
    seriesColors,
    seriesLabels,
    getMetricValue,
    getQuality,
    getQualityBreakdown,
    getSampleSize,
    model_info,
    run_configs,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)
    const resizeObserver = new ResizeObserver(() => chartInstance?.resize())
    resizeObserver.observe(node)
    updateChart()
    return {
      destroy() {
        resizeObserver.disconnect()
        chartInstance?.dispose()
        chartInstance = null
      },
    }
  }
</script>

<div class="bg-white border border-gray-200 rounded-lg p-6 flex flex-col">
  <div class="flex flex-row gap-4 items-start">
    <div class="flex-grow">
      <div class="text-xl font-bold">Price vs Latency</div>
      <div class="text-sm text-gray-500">{subtitle}</div>
    </div>
    <div class="flex flex-row gap-1 items-center flex-shrink-0">
      <!-- The page owns the gate - it is in the URL - so it supplies the
           control -->
      <slot name="controls" />
      <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
    </div>
  </div>

  {#if hasData}
    <div use:initChart class="w-full flex-1 min-h-[460px] mt-4"></div>
  {:else}
    <ChartNoData
      title={selectedRunConfigIds.length === 0
        ? "Pin configs to compare"
        : "Not enough configs with cost and speed"}
      message={selectedRunConfigIds.length === 0
        ? "Select a run config, or hover a card and hit Pin, to build a compare set."
        : `This chart needs ${MIN_PRICE_LATENCY_POINTS} run configs with both a cost and a latency recorded, and this comparison has ${built.plotted.length}.`}
    />
  {/if}

  <!-- Under the plot in both states: what was left off is a fact about the
       comparison, not about the picture, and it is most needed exactly when
       there is no picture. -->
  <div class="text-xs text-gray-400 mt-3">
    {#if omissionNote}
      <span>{omissionNote}</span>
    {/if}
    <span>{LATENCY_CAVEAT}</span>
  </div>
</div>

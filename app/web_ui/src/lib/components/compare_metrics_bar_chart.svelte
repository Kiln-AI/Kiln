<script lang="ts">
  // The performance-metrics chart: cost, latency, token usage and call counts,
  // as a sibling to the eval-score radar rather than more axes on it.
  //
  // Splitting them is not just tidiness. The two charts answer different
  // questions ("is it right" vs "what did it cost") and, more importantly, they
  // are scaled differently and cannot honestly share a ring:
  //
  //   - an eval score has its own range (0-1 for pass/fail, 1-5 for five star)
  //     and higher is better, so it can be plotted against an absolute scale.
  //   - a metric has no range at all - there is no maximum cost - so the only
  //     meaningful scale is position among the configs on the chart. See
  //     relative_metric_score.
  //
  // BARS, not a second radar, and the relative scale is the reason. A radar
  // reads as a shape: the polygon's area and its lopsidedness are what the eye
  // takes from it, and both are artefacts here, because a metric's score is its
  // rank among the plotted configs and the ORDER of the axes is a curatorial
  // choice. Rotating the axis list changes the shape without changing a single
  // number. What the reader actually comes here to do is answer one metric at a
  // time - "which of these is cheapest, and by how much" - and that is a length
  // comparison against a common baseline, which is the one judgement bars make
  // easy and a ring of radii makes hard. Bars also survive the dozen pinned
  // configs this page allows, where a dozen overlapping polygons is mud.
  //
  // One grammar, and it is carried by the labels rather than by a caption:
  // every row is named for the virtue it measures ("Cost Efficiency", not
  // "Cost"; "Skill Read Efficiency", not "Skill Reads Repeat"), so a longer bar
  // reads as better on a glance instead of needing the reader to remember that
  // this chart is inverted. Which end of a raw scale is the good one lives on
  // the row itself, since it is not always the low end - cache reuse is better
  // the more of it there is. See $lib/utils/evolution/metric_axes for the
  // naming, the families and the direction of each metric.
  //
  // Because the scale is a comparison, one run config has nothing to be scored
  // against - it would sit at the midpoint of every row and draw a straight
  // edge of equal bars that looks like a result but is an artefact. That case
  // is refused explicitly below rather than rendered.

  import * as echarts from "echarts"
  import type {
    TaskRunConfig,
    ProviderModels,
    PromptResponse,
  } from "$lib/types"
  import { isMcpRunConfig } from "$lib/types"
  import {
    getRunConfigModelDisplayName,
    getRunConfigPromptDisplayName,
    getRunConfigInputTransformSummaryLabel,
  } from "$lib/utils/run_config_formatters"
  import { relative_metric_score } from "$lib/utils/relative_metric_score"
  import {
    format_metric_value,
    wrap_axis_label,
    metric_family_bands,
    metric_chart_empty_state,
    MIN_METRIC_AXES,
    MIN_METRIC_CONFIGS,
    type MetricAxis,
  } from "$lib/utils/evolution/metric_axes"
  import {
    category_band,
    family_band_span,
    type BarPlot,
  } from "$lib/utils/evolution/metric_bars"
  import {
    axis_help_html,
    metric_axis_help,
  } from "$lib/utils/evolution/axis_help"
  import {
    family_label_budgets,
    family_tone,
    truncate_to_width,
    type FamilyBand,
  } from "$lib/utils/evolution/family_bands"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  // The metrics to plot, already narrowed to the user's selection by the page
  export let axes: MetricAxis[] = []
  // Raw value of a metric for a run config, in its own units. Null when the
  // config has no number for it.
  export let getMetricValue: (runConfigId: string, key: string) => number | null
  export let run_configs: TaskRunConfig[] = []
  export let model_info: ProviderModels | null = null
  export let prompts: PromptResponse | null = null
  export let selectedRunConfigIds: string[] = []
  // Rendered under the subtitle - what the page left off and why
  export let notShownNote: string | null = null
  // Which slice of the dataset these numbers are over, when it is not the
  // whole of what the page normally shows. Named in the subtitle rather than
  // left to a control elsewhere on the page: cost per run on a 25-item train
  // split is a different claim from cost per run on the test set, and a chart
  // that does not say which one it is inviting the wrong comparison.
  export let scopeLabel: string | null = null
  // How many metrics the Metrics menu can offer, switched on or not. `axes` is
  // only the ones that are on, so without this the chart cannot tell "the
  // reader switched the rest off" from "there are no others", and an empty
  // chart on a task with two metrics sends them to a menu with nothing more in
  // it.
  export let availableAxisCount: number = 0
  // How many metrics the row-hide x took out of the comparison. The Metrics
  // menu does not offer these back - only the table's own Hidden control does -
  // so an empty chart has to name whichever of the two can help.
  export let hiddenAxisCount: number = 0

  // At least what is already on the chart: a caller that reports no inventory
  // is taken to have handed over everything it has.
  $: availableAxes = Math.max(availableAxisCount, axes.length)

  const SCALE_TOOLTIP = `Each row is named for the quality it measures, so a longer bar is better on every one of them - cheaper, faster, leaner, more cache reuse.

Scores are **relative to the other run configs on the chart**, on a shared 0-100 scale: unlike a pass rate, cost and latency have no maximum to plot against, so there is no "full scale" mode here. The bar is that score; the raw quantity behind it is in the tooltip and in the table below.

Related metrics sit together: reading **down** the chart the rows go cost, tokens, calls, speed, responsiveness. Each family is named down the left, over the bar that marks how far it runs. Switching metrics off in the Metrics menu keeps the grouping.

Because it is a comparison, at least two run configs are needed.`

  const AXIS_MAX = 100
  const LABEL_COLOR = "#666"

  // The family band: a thin bar down the gutter, broken between families, with
  // the family's name written along it.
  //
  // Sixteen row names in one weight of grey read as an undifferentiated list
  // even though the families behind them are contiguous, so the grouping needs
  // to be a property of the image rather than of the data. The band is drawn
  // OUTSIDE the plot on purpose: the run configs are the subject of this chart,
  // and a tint swept under the bars would sit beneath every one of them and
  // change what a series looks like from one family to the next.
  //
  // The name is what turns the bar from a divider into a heading, and it is set
  // larger and darker than the row names so the gutter reads as five groups of
  // metrics rather than sixteen loose ones. It is laid ALONG the band, reading
  // up, because a horizontal name would cost the plot its width - see
  // family_band_label on the radar side for the same trade. The tone is shared
  // with the radars (family_bands): one neutral ink, laddered by opacity from
  // lightest at the top to darkest at the bottom, and no hue, because the run
  // configs already own colour here. The NAME does not ladder with its band -
  // see FAMILY_LABEL_COLOR.
  const BAND_THICKNESS = 4
  const BAND_LABEL_GAP = 7
  // The break between two families, in px of gutter
  const BAND_ROW_GAP = 10
  // Room for the name laid along the band. Its LINE HEIGHT, not its width: it
  // runs down the gutter, so this is all the width the whole tier costs.
  const FAMILY_LABEL_LINE_HEIGHT = 15
  const FAMILY_LABEL_FONT_SIZE = 13
  const FAMILY_LABEL_FONT = `600 ${FAMILY_LABEL_FONT_SIZE}px InterVariable, Inter, system-ui, sans-serif`
  const FAMILY_LABEL_CHAR_WIDTH = 8
  // One weight for every family name, deliberately NOT its own band's tone. The
  // band says where the family falls in the chain; the name says which family
  // it is, and identity is not a quantity. A name that laddered with its band
  // would also make the heading at the top - the lightest rung, and the first
  // one a reader lands on - the least legible text on the card.
  const FAMILY_LABEL_COLOR = "#4b5563"
  // Clear space between the name and the row names beside it
  const FAMILY_LABEL_TAIL_GAP = 8
  // Clear space between two family names, and so the inset a name is cut to
  // inside its own band
  const FAMILY_LABEL_INSET = 8

  // Row names, for solving the gutter. Measured rather than estimated: the
  // whole width of the widest one comes out of the plot. The per-character
  // fallback is for a context that cannot measure text (jsdom); it only has to
  // be conservative, since nothing is drawn there anyway.
  const ROW_LABEL_FONT_SIZE = 11
  const ROW_LABEL_LINE_HEIGHT = 14
  const ROW_LABEL_FONT = `${ROW_LABEL_FONT_SIZE}px InterVariable, Inter, system-ui, sans-serif`
  const ROW_LABEL_CHAR_WIDTH = 6.6
  // Between a row name and the baseline its bars grow from
  const ROW_LABEL_GAP = 10
  // A row name may not take more of the card than this. Names arrive wrapped to
  // two short lines, so this is a backstop against a card narrow enough that
  // the plot would otherwise be squeezed to nothing, not the normal path.
  const ROW_LABEL_MAX_FRACTION = 0.34
  const CHART_PAD = 4
  // The last value label ("100") is centred on the plot's right edge, so half
  // of it hangs past
  const VALUE_LABEL_OVERHANG = 14
  // The value labels under the plot
  const VALUE_AXIS_HEIGHT = 22

  // Thin marks: a bar is a length, and a fat one is a block whose length is
  // harder to read off. Capped rather than fixed, so three configs do not draw
  // three slabs in a tall card - echarts keeps them centred in their row.
  const BAR_MAX_WIDTH = 26

  // The bottom legend, which the plot has to sit above: one line for the run
  // config's name plus one per line of subtext, at the line heights set below.
  const LEGEND_NAME_LINE_HEIGHT = 16
  const LEGEND_SUB_LINE_HEIGHT = 14
  const LEGEND_PADDING = 10

  let chartInstance: echarts.ECharts | null = null
  // The drawing box, tracked because the gutter and the family band are solved
  // from it in px rather than left to echarts' percentages
  let boxWidth = 0
  let boxHeight = 0

  function getSeriesDisplayName(config: TaskRunConfig): string {
    if (config.name) return config.name
    if (isMcpRunConfig(config.run_config_properties)) {
      return config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
    }
    return getRunConfigModelDisplayName(config, model_info) ?? "Unknown"
  }

  // Run configs that will actually be drawn: selected, resolvable, and with at
  // least one metric to their name. A config with nothing to plot must not count
  // towards the two needed to make a comparison.
  $: plottedConfigs = selectedRunConfigIds
    .map((configId) => run_configs.find((config) => config.id === configId))
    .filter((config): config is TaskRunConfig => !!config?.id)
    .filter((config) =>
      axes.some(
        (axis) => getMetricValue(config.id as string, axis.key) !== null,
      ),
    )

  // Only metrics every plotted config has a value for. A missing value draws no
  // bar, which on a row of bars is indistinguishable from scoring worst on it -
  // so a metric one config has no number for cannot be drawn honestly at all.
  // It is left out and counted under the title.
  $: plottedAxes = axes.filter((axis) =>
    plottedConfigs.every(
      (config) => getMetricValue(config.id as string, axis.key) !== null,
    ),
  )
  $: incompleteAxisCount = axes.length - plottedAxes.length

  // The family runs as they will actually be drawn. Derived from the plotted
  // metrics rather than the selected ones, so a metric switched off in the
  // Metrics menu - or dropped for having no number on every config - takes its
  // share of the gutter with it, and a family emptied that way leaves neither
  // an orphaned band nor a name in the key. See metric_family_bands for the
  // single-family case, where there is no boundary to draw and the band is
  // silent.
  $: familyBands = metric_family_bands(plottedAxes)

  $: enoughConfigs = plottedConfigs.length >= MIN_METRIC_CONFIGS
  $: hasData = enoughConfigs && plottedAxes.length >= MIN_METRIC_AXES
  // No chart, or only one family, means no bands - and a key to bands that are
  // not there would be worse than no key at all.
  $: showFamilyKey = hasData && familyBands.length > 0

  // Why the chart is empty, and which control fixes it. The counts go out to
  // metric_chart_empty_state whole rather than being tested here, because the
  // ORDER the questions are asked in is the load-bearing part: `plottedConfigs`
  // is counted through the metrics, so with none selected the config test
  // collapses to "nothing to compare against" for a reader whose configs are
  // pinned and do have results.
  $: noData = metric_chart_empty_state({
    selected: axes.length,
    plotted: plottedAxes.length,
    available: availableAxes,
    hidden: hiddenAxisCount,
    configs: plottedConfigs.length,
  })

  $: shownNote = (() => {
    const parts: string[] = []
    if (incompleteAxisCount > 0) {
      parts.push(
        `${incompleteAxisCount} ${
          incompleteAxisCount === 1 ? "metric" : "metrics"
        } without results for every selected run config`,
      )
    }
    if (notShownNote) parts.push(notShownNote)
    if (parts.length === 0) return null
    return `Not shown: ${parts.join(", ")}. See the table below.`
  })()

  // Colour follows the run config: pinned order is series order here and data
  // order on the quality radar, and both take the palette by that index, so a
  // config is the same colour on both charts of the pair. Read back off the
  // option rather than restated, since the palette is the theme's.
  function seriesColorAt(index: number): string {
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return "#888"
    return palette[index % palette.length]
  }

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  // The row is labelled with the virtue, so the tooltip is where the raw
  // quantity behind it is spelled out - "Cost Efficiency" over "Cost · usage
  // rollup" - along with where the number came from.
  function axisSubtitle(axis: MetricAxis): string {
    return `${axis.valueLabel} · ${axis.evalName ?? "usage rollup"}`
  }

  // One metric across every plotted config, so hovering a row answers "how do
  // they compare here" rather than reciting everything one config used. The
  // relative score is what the bar shows, so the raw quantity comes with it -
  // the score alone is unreadable as a cost. Ordered as the bars are, which is
  // the order the legend is in.
  function buildAxisTooltip(
    axisIndex: number,
    chartAxes: MetricAxis[],
  ): string {
    const axis = chartAxes[axisIndex]
    if (!axis) return ""

    let html = `<div style="font-weight: bold;">${axis.label}</div>
      <div style="color: #888; margin-bottom: 6px;">${axisSubtitle(axis)}</div>`
    plottedConfigs.forEach((config, index) => {
      const name = getSeriesDisplayName(config)
      const rawValue = getMetricValue(config.id as string, axis.key)
      const score = scoreFor(config, axis)
      const shown =
        rawValue === null || score === null
          ? "N/A"
          : `${score.toFixed(1)} <span style="color: #888;">(${format_metric_value(
              axis.unit,
              rawValue,
            )})</span>`
      html += `<div>${tooltipMarker(seriesColorAt(index))}${name}: ${shown}</div>`
    })
    return html
  }

  // The legend keeps the whole-config summary: what it is, and its raw numbers.
  function buildRunConfigTooltip(
    name: string,
    chartAxes: MetricAxis[],
  ): string {
    const config = run_configs.find(
      (candidate) => getSeriesDisplayName(candidate) === name,
    )

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${name}</div>`
    if (config && isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      html += `<div>MCP Tool: ${toolName}</div>`
    } else {
      const modelName = config
        ? getRunConfigModelDisplayName(config, model_info) || "Unknown"
        : "Unknown"
      html += `<div>Model: ${modelName}</div>`
      const promptName = config
        ? getRunConfigPromptDisplayName(config, prompts)
        : null
      if (promptName) html += `<div>Prompt: ${promptName}</div>`
      if (config) {
        const transformLabel = getRunConfigInputTransformSummaryLabel(config)
        if (transformLabel) {
          html += `<div>Input Transform: ${transformLabel}</div>`
        }
      }
    }

    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">Values</div>`
    for (const axis of chartAxes) {
      const rawValue = config?.id ? getMetricValue(config.id, axis.key) : null
      // The raw quantity's own name, not the row label: "Cost: $0.0123", not
      // "Cost Efficiency: $0.0123", which would read as a score.
      html += `<div>${axis.valueLabel}: ${format_metric_value(
        axis.unit,
        rawValue,
      )}</div>`
    }
    return html
  }

  function buildLegendSubtext(config: TaskRunConfig): string {
    const parts: string[] = []
    if (isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      parts.push(`{sub|Tool: ${toolName}}`)
    } else {
      const modelName =
        getRunConfigModelDisplayName(config, model_info) || "Unknown"
      const promptName = getRunConfigPromptDisplayName(config, prompts)
      parts.push(`{sub|Model: ${modelName}}`)
      if (promptName) parts.push(`{sub|Prompt: ${promptName}}`)
      const transformLabel = getRunConfigInputTransformSummaryLabel(config)
      if (transformLabel) parts.push(`{sub|Input Transform: ${transformLabel}}`)
    }
    return parts.join("\n")
  }

  // One canvas for the life of the component: measuring text needs a 2d context
  // and creating one per redraw is pure waste.
  let textMeasurer: CanvasRenderingContext2D | null | undefined

  function measureIn(font: string, charWidth: number, text: string): number {
    if (textMeasurer === undefined) {
      textMeasurer = document.createElement("canvas").getContext("2d")
    }
    if (!textMeasurer) return text.length * charWidth
    textMeasurer.font = font
    return textMeasurer.measureText(text).width
  }

  function measureRowWidth(text: string): number {
    return measureIn(ROW_LABEL_FONT, ROW_LABEL_CHAR_WIDTH, text)
  }

  function measureFamilyWidth(text: string): number {
    return measureIn(FAMILY_LABEL_FONT, FAMILY_LABEL_CHAR_WIDTH, text)
  }

  // What the bottom legend will occupy, from the subtext it is actually going
  // to carry - an MCP config prints one line under its name, a model-and-prompt
  // config three - so the plot is never held off by room nothing will use.
  function legendHeight(): number {
    let subLines = 0
    for (const config of plottedConfigs) {
      subLines = Math.max(
        subLines,
        buildLegendSubtext(config).split("\n").length,
      )
    }
    return (
      LEGEND_PADDING +
      LEGEND_NAME_LINE_HEIGHT +
      subLines * LEGEND_SUB_LINE_HEIGHT
    )
  }

  // How far outside a name's own box a pointer still counts as being on it.
  // An 11px line of text is a small target, and the reader is aiming at a
  // word rather than at a rectangle they cannot see.
  const AXIS_HOVER_PAD = 4

  interface BarLayout {
    /** Where the plot starts, i.e. the baseline the bars grow from */
    gridLeft: number
    /** Widest row name, as drawn */
    labelWidth: number
    /** The rows, for placing anything that has to line up with one */
    plot: BarPlot
  }

  // Everything outside the plot, solved in px.
  //
  // The gutter is the whole of the layout problem on this chart: the family
  // tier and the row names come out of the plot's width, and the plot is what
  // the reader is actually reading. Both are measured rather than reserved
  // generously - a name is right-aligned against the baseline, so its full
  // width counts - and the names are capped at a fraction of the card so a
  // narrow one keeps a plot at all.
  function barLayout(names: string[]): BarLayout {
    const measured = Math.max(
      0,
      ...names.map((name) =>
        Math.max(...name.split("\n").map(measureRowWidth)),
      ),
    )
    const familyTier =
      familyBands.length > 0
        ? BAND_THICKNESS +
          BAND_LABEL_GAP +
          FAMILY_LABEL_LINE_HEIGHT +
          FAMILY_LABEL_TAIL_GAP
        : 0
    const labelWidth = Math.min(
      measured,
      Math.max(0, boxWidth * ROW_LABEL_MAX_FRACTION),
    )
    const gridLeft = CHART_PAD + familyTier + labelWidth + ROW_LABEL_GAP
    const top = CHART_PAD
    const height = Math.max(
      0,
      boxHeight - top - legendHeight() - VALUE_AXIS_HEIGHT,
    )
    return { gridLeft, labelWidth, plot: { top, height } }
  }

  // One invisible box per row name, carrying what that metric measures.
  //
  // The names are echarts' own, which leaves nothing of ours under the pointer
  // to hang a tooltip on, so the boxes are placed against the same band
  // arithmetic echarts lays the rows out with - see metric_bars.
  //
  // Transparent rather than `invisible`, which zrender still hit-tests: a fill
  // nobody can see is the honest way to say "this is here to be hovered".
  function axisHelpGraphics(
    chartAxes: MetricAxis[],
    names: string[],
    layout: BarLayout,
  ) {
    return chartAxes.map((axis, index) => {
      const row = category_band(index, chartAxes.length, layout.plot)
      const lines = names[index]?.split("\n").length ?? 1
      const height = lines * ROW_LABEL_LINE_HEIGHT
      const help = axis_help_html(metric_axis_help(axis))
      return {
        type: "rect",
        // Over the family band, which reaches into the same gutter
        z: 200,
        // Nothing to click, so nothing that says there is
        cursor: "default",
        shape: {
          x:
            layout.gridLeft -
            ROW_LABEL_GAP -
            layout.labelWidth -
            AXIS_HOVER_PAD,
          y: row.center - height / 2 - AXIS_HOVER_PAD,
          // Up to the plot's edge and no further: a box overhanging the
          // baseline would take the first pixels of every bar's own row
          // tooltip.
          width: layout.labelWidth + ROW_LABEL_GAP + AXIS_HOVER_PAD,
          height: height + AXIS_HOVER_PAD * 2,
        },
        style: { fill: "transparent" },
        // echarts' own tooltip, so hovering a name and hovering a bar are two
        // views of the same object rather than two popup styles
        tooltip: { formatter: () => help },
      }
    })
  }

  // One bar per family run plus the family's name, drawn as graphics: the plot
  // itself only knows about rows, and this tier lives beside them.
  function bandGraphics(bands: FamilyBand[], rows: number, layout: BarLayout) {
    const spans = bands.map((band) =>
      family_band_span(band, rows, layout.plot, BAND_ROW_GAP),
    )
    // A name may run past its own band into a neighbour's unused room, which is
    // what keeps a one-row family from coming out as "Respo…" beside a
    // three-row one with an inch of empty gutter. Same rule as the ring - see
    // family_label_budgets - and the wrap it does between the first and last
    // band, which are genuinely adjacent around a circle and are not down a
    // column, only ever makes the two ends borrow LESS than they could.
    const budgets = family_label_budgets(
      bands.map((band) => measureFamilyWidth(band.label)),
      spans.map((span) => span.height),
      FAMILY_LABEL_INSET,
    )
    return bands.flatMap((band, index) => {
      const span = spans[index]
      const text = truncate_to_width(
        band.label,
        budgets[index],
        measureFamilyWidth,
      )
      return [
        {
          type: "rect",
          // Inert, like every mark in the gutter: the row tooltip is echarts'
          // own axis tooltip, and anything that could become the event target
          // first would suppress it.
          silent: true,
          z: 0,
          shape: {
            x: CHART_PAD,
            y: span.top,
            width: BAND_THICKNESS,
            height: span.height,
            r: BAND_THICKNESS / 2,
          },
          style: { fill: family_tone(index, bands.length) },
        },
        ...(text
          ? [
              {
                type: "text",
                silent: true,
                z: 100,
                x:
                  CHART_PAD +
                  BAND_THICKNESS +
                  BAND_LABEL_GAP +
                  FAMILY_LABEL_LINE_HEIGHT / 2,
                y: span.top + span.height / 2,
                // Read up the gutter, the one direction that costs the plot a
                // line height instead of a name's full width
                rotation: Math.PI / 2,
                style: {
                  text,
                  align: "center",
                  verticalAlign: "middle",
                  fontSize: FAMILY_LABEL_FONT_SIZE,
                  fontWeight: 600,
                  fill: FAMILY_LABEL_COLOR,
                },
              },
            ]
          : []),
      ]
    })
  }

  // Every value on a metric, so each config can be scored by its position among
  // them. Rebuilt per draw from the plotted set, since the scale IS that set.
  let scoresByAxis = new Map<string, Map<string, number>>()

  function scoreFor(config: TaskRunConfig, axis: MetricAxis): number | null {
    const scores = scoresByAxis.get(axis.key)
    const score = scores?.get(config.id as string)
    return score === undefined ? null : score
  }

  function generateChartData(): {
    names: string[]
    series: { name: string; data: number[] }[]
    legend: string[]
    chartAxes: MetricAxis[]
  } {
    const chartAxes = plottedAxes
    const names = chartAxes.map((axis) => wrap_axis_label(axis.label))

    // Direction correction lives in relative_metric_score, pointed by the
    // metric: the best raw value gets the highest score, which is what gives
    // the cheapest and fastest config the longest bar.
    scoresByAxis = new Map()
    for (const axis of chartAxes) {
      const values = plottedConfigs
        .map((config) => getMetricValue(config.id as string, axis.key))
        .filter((value): value is number => value !== null)
      const scores = new Map<string, number>()
      for (const config of plottedConfigs) {
        // Every plotted config has a value for every plotted metric by
        // construction
        scores.set(
          config.id as string,
          relative_metric_score(
            getMetricValue(config.id as string, axis.key) as number,
            values,
            { higherIsBetter: axis.better === "higher" },
          ),
        )
      }
      scoresByAxis.set(axis.key, scores)
    }

    const series: { name: string; data: number[] }[] = []
    const legend: string[] = []
    for (const config of plottedConfigs) {
      const name = getSeriesDisplayName(config)
      legend.push(name)
      series.push({
        name,
        data: chartAxes.map((axis) => scoreFor(config, axis) ?? 0),
      })
    }

    return { names, series, legend, chartAxes }
  }

  function updateChart() {
    if (!chartInstance) return
    if (!hasData) {
      chartInstance.clear()
      return
    }
    // The gutter and the rows are solved from the box, so there is nothing to
    // draw until the box has been measured. The ResizeObserver fires on
    // observe, so this only skips the render before the first frame.
    if (boxWidth <= 0 || boxHeight <= 0) return

    const { names, series, legend, chartAxes } = generateChartData()
    const layout = barLayout(names)

    const legendFormatter: Record<string, string> = {}
    for (const config of plottedConfigs) {
      const displayName = getSeriesDisplayName(config)
      legendFormatter[displayName] =
        `${displayName}\n${buildLegendSubtext(config)}`
    }

    chartInstance.setOption(
      {
        tooltip: {
          // Per ROW, not per bar: the question a metric row is read to answer
          // is "how do these configs compare here", and a bar chart can say it
          // natively - the radar had to work the hovered axis out from the
          // pointer's angle because a radar tooltip is per-series.
          trigger: "axis",
          axisPointer: { type: "shadow" },
          confine: true,
          formatter: (
            params: { dataIndex: number; seriesName?: string }[] | undefined,
          ) => {
            const hovered = params?.[0]
            if (!hovered) return ""
            return buildAxisTooltip(hovered.dataIndex, chartAxes)
          },
        },
        legend: {
          data: legend,
          // Clicking a legend entry hides/shows that run config's bars - with a
          // dozen configs allowed, isolating one is the only way to read the
          // chart. Same behaviour as the eval-score radar.
          selectedMode: true,
          formatter: (name: string) => legendFormatter[name] || name,
          tooltip: {
            show: true,
            formatter: (params: { name: string }) =>
              buildRunConfigTooltip(params.name, chartAxes),
          },
          textStyle: {
            lineHeight: 16,
            rich: {
              sub: {
                fontSize: 11,
                color: "#666",
                lineHeight: 14,
              },
            },
          },
          orient: "horizontal" as const,
          bottom: 0,
          left: "center" as const,
          itemGap: 24,
          // This chart sits in a column beside the eval-score radar, so a
          // wrapping legend would eat the plot. Scroll keeps it to one row.
          type: "scroll" as const,
        },
        graphic: [
          ...bandGraphics(familyBands, chartAxes.length, layout),
          ...axisHelpGraphics(chartAxes, names, layout),
        ],
        grid: {
          left: layout.gridLeft,
          right: CHART_PAD + VALUE_LABEL_OVERHANG,
          top: layout.plot.top,
          height: layout.plot.height,
          // The gutter is already solved in px, and containLabel would solve it
          // again from the labels alone - leaving the family tier overlapping
          // the names it is meant to sit beside.
          containLabel: false,
        },
        xAxis: {
          type: "value",
          min: 0,
          max: AXIS_MAX,
          interval: 25,
          axisLabel: {
            color: "#9ca3af",
            fontSize: 10,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          splitLine: {
            lineStyle: { color: "#e5e7eb", type: "dashed" as const },
          },
        },
        yAxis: {
          type: "category",
          data: names,
          // Cost first, at the top: the families are ordered as a chain and the
          // chart is read down. echarts puts category 0 at the bottom of a
          // vertical axis otherwise.
          inverse: true,
          axisLabel: {
            color: LABEL_COLOR,
            fontSize: ROW_LABEL_FONT_SIZE,
            lineHeight: ROW_LABEL_LINE_HEIGHT,
            margin: ROW_LABEL_GAP,
            // Names arrive pre-wrapped from wrap_axis_label. The width is the
            // cap the gutter was solved against, so a name that would have
            // taken a third of the card is cut rather than paid for.
            width: layout.labelWidth,
            overflow: "truncate" as const,
          },
          axisLine: { show: false },
          axisTick: { show: false },
          // Alternating rows, so a bar is read against its own name across a
          // gutter rather than by counting down from the top
          splitArea: {
            show: true,
            areaStyle: { color: ["#f8f9fa", "#ffffff"] },
          },
        },
        series: series.map((entry) => ({
          name: entry.name,
          type: "bar" as const,
          data: entry.data,
          barMaxWidth: BAR_MAX_WIDTH,
          // A gap of surface between neighbouring bars, and rounded ends on the
          // value end only - the baseline end stays square, because that is
          // where the length is measured from.
          barGap: "15%",
          barCategoryGap: "35%",
          itemStyle: {
            borderRadius: [0, 3, 3, 0] as [number, number, number, number],
          },
        })),
      },
      true,
    )
  }

  // Redraw when anything that changes the picture changes. Every input has to
  // be referenced here, or the chart keeps showing the previous render.
  // getMetricValue is passed through rather than tested: it is always defined,
  // so a truthiness check would be meaningless, but referencing it is what
  // makes a rebuilt getter (the page rebuilds one when lazily fetched usage
  // arrives) count as a dependency.
  $: redraw(
    chartInstance,
    axes,
    plottedAxes,
    familyBands,
    plottedConfigs,
    selectedRunConfigIds,
    getMetricValue,
    model_info,
    prompts,
    // The gutter and the family band are solved from the box, so a resize is a
    // redraw and not just an echarts resize()
    boxWidth,
    boxHeight,
  )
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  function redraw(..._dependencies: unknown[]) {
    updateChart()
  }

  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)
    // Measured up front as well as from the observer, whose first callback is a
    // frame away - otherwise the first paint is an empty chart.
    boxWidth = node.clientWidth
    boxHeight = node.clientHeight

    // Resizing the canvas is not enough on its own: the gutter, the rows and
    // the family band are all in px, solved from the box, so the new size has
    // to reach the reactive statement that redraws them.
    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
      boxWidth = node.clientWidth
      boxHeight = node.clientHeight
    })
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

<div
  class="bg-white border border-gray-200 rounded-lg p-6 h-full flex flex-col"
>
  <div class="flex flex-row gap-4 items-start">
    <div class="flex-grow">
      <div class="text-xl font-bold">Performance Metrics</div>
      <div
        class="text-sm text-gray-500 {shownNote || showFamilyKey ? '' : 'mb-4'}"
      >
        Cost, speed and usage for the selected run configurations.{scopeLabel
          ? ` ${scopeLabel} only.`
          : ""} A longer bar is better on every metric.
      </div>
      {#if shownNote}
        <div class="text-xs text-gray-400 mt-1 {showFamilyKey ? '' : 'mb-4'}">
          {shownNote}
        </div>
      {/if}
      {#if showFamilyKey}
        <!-- The gutter says which family is which and where each one ends; what
             it cannot say without being counted is HOW MANY metrics each
             covers, so that is all this line is for. No swatch, and no colour:
             the band tones are a separator, not an identity, and a key to them
             would invite reading them as one. Both this and the bands are built
             from the same runs, so a metric switched off cannot leave a name
             here without a band on the chart. -->
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 mb-4">
          <span class="text-xs text-gray-400"> Metric families: </span>
          {#each familyBands as band}
            <span class="text-xs text-gray-500">
              {band.label}
              <span class="text-gray-400">{band.count}</span>
            </span>
          {/each}
        </div>
      {/if}
    </div>
    <div class="flex flex-row gap-1 items-center flex-shrink-0">
      <!-- The page owns which metrics are on, so it supplies the control -->
      <slot name="controls" />
      <InfoTooltip tooltip_text={SCALE_TOOLTIP} position="bottom" />
    </div>
  </div>
  {#if hasData}
    <!-- Matches the eval-score radar's bottom-legend box, so the two charts
         line up when they sit side by side. -->
    <div use:initChart class="w-full flex-1 min-h-[640px]"></div>
  {:else}
    <ChartNoData title={noData.title} message={noData.message} />
  {/if}
</div>

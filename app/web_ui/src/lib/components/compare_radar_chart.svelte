<script lang="ts" context="module">
  // One eval's section of the comparison table, as fed to the chart. Exported
  // so pages that build these don't have to redeclare the shape.
  export type ComparisonFeature = {
    category: string
    items: { label: string; key: string }[]
    has_default_eval_config: boolean | undefined
    eval_id: string
  }
</script>

<script lang="ts">
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
  import { formatLatency } from "$lib/utils/formatters"
  import { relative_metric_score } from "$lib/utils/relative_metric_score"
  import {
    FALLBACK_SERIES_COLOR,
    series_label,
  } from "$lib/utils/evolution/series_identity"
  import {
    family_bands,
    family_band_arc,
    family_band_label,
    family_label_budgets,
    family_label_reach,
    family_tone,
    truncate_to_width,
    type FamilyBand,
  } from "$lib/utils/evolution/family_bands"
  import {
    fit_radar,
    nearest_axis_index,
    place_labels_on_rays,
    type RadarAxisLabel,
  } from "$lib/utils/evolution/metric_axes"
  import {
    axis_help_html,
    quality_axis_help,
  } from "$lib/utils/evolution/axis_help"
  import ChartNoData from "$lib/components/chart_no_data.svelte"
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"

  // Props
  export let comparisonFeatures: ComparisonFeature[]
  export let getModelValueRaw: (
    modelKey: string | null,
    dataKey: string,
  ) => number | null
  export let run_configs: TaskRunConfig[]
  export let model_info: ProviderModels | null
  export let prompts: PromptResponse | null = null
  export let selectedRunConfigIds: string[]
  // Full-range maximum for a data key (eg 1 for pass/fail, 5 for 5-star), used by
  // the "Full Scale" axis mode. Keys without an entry (unbounded custom scores)
  // fall back to the data-relative max.
  export let scoreAxisMaxes: Record<string, number> = {}
  // Improvement direction per data key: "higher_is_better" | "lower_is_better" |
  // "informational". Unknown keys are treated as higher-is-better, which is what
  // every rating scale is by definition.
  export let scoreDirections: Record<string, string> = {}
  // Where the legend sits. "side" (default) keeps the historical behavior: a
  // vertical legend to the right of the radar, which collapses to a horizontal
  // one underneath when there are at most two series. "bottom" always puts a
  // scrollable horizontal legend underneath, so it can never paint over the
  // right-hand axis labels — for narrow columns with many configs.
  export let legend_position: "side" | "bottom" = "side"
  // Whether the LEGEND belongs to the page rather than to this card.
  //
  // Compare V2 draws one legend above three charts (evolution_legend.svelte),
  // because three name-keyed echarts legends over three views of one
  // comparison toggle independently: switching a config off to read the radar
  // left it on the bars and the parallel chart beside it. This card then draws
  // none of its own and gives the room back to the ring. The older compare
  // page has no such legend and keeps this off, so it is unchanged.
  //
  // Separate from `legend_position` on purpose: bottom mode is a GEOMETRY -
  // hand-placed axis names, family arcs solved in px - that Compare V2 needs
  // whether or not it draws a legend, and folding "no legend" into that enum
  // would tie the two together.
  export let external_legend: boolean = false
  // Colour per run config id, decided by the page (see series_color_map) so a
  // config keeps ONE colour across every chart that plots it. Empty - the
  // default, and what the older compare page passes - falls back to the theme
  // palette by series index, which is what this chart always did.
  export let seriesColors: Record<string, string> = {}
  // What to CALL each run config, by id, when the page has decided that for
  // the whole comparison - see series_display_map, which leads with the model
  // and only falls back to the config's name where a model is shared. This
  // chart's series names, its legend keys and every tooltip that prints a
  // config go through it.
  //
  // Empty - the default, and what the older compare page passes - falls back
  // to series_label, the config-name-first naming this chart has always used.
  // That page has no unified legend to lead with a model, so it is unchanged.
  export let seriesLabels: Record<string, string> = {}
  // Family per data key, for grouping the ring. The page resolves these from
  // the task's own metadata (see $lib/utils/evolution/score_families) rather
  // than this chart classifying anything, and supplies them already ordered:
  // the axes arrive family by family, so a band is a run of equal labels.
  //
  // Empty - the default, and what a task with no declared grouping produces -
  // means no bands and no key, and the chart is exactly what it was before
  // families existed. Only honoured in "bottom" mode, where the geometry is
  // solved in px: "side" mode leaves the ring to echarts' percentages, and an
  // arc cannot be placed against a radius nobody has computed.
  export let axisFamilies: Record<string, { id: string; label: string }> = {}
  // What each eval's criterion actually says, keyed by eval id, for the popup
  // that appears when the reader hovers an axis name. Resolved by the page from
  // the task's own Specs - see $lib/utils/evolution/axis_help - because the
  // chart has no business knowing what a spec is.
  //
  // Empty is the ordinary case for a task that has written no specs, and for
  // the older compare page, which does not fetch them. An axis with no entry
  // still names the eval it came from; one that cannot even do that gets no
  // popup rather than a box repeating its own label.
  export let specDescriptions: Record<string, string> = {}
  // Card heading. Defaults are the historical text, so the older compare page -
  // which also plots usage axes here - is unchanged; Compare V2 passes the
  // Quality-track naming that pairs this card with the metrics one beside it.
  export let title: string = "Radar Chart"
  export let subtitle: string =
    "Compare the evaluation scores of the run configurations selected above."
  // Where the comparison table sits relative to this card, so the notes that
  // point at it are true on both pages that use this chart: the older compare
  // page puts its table above, Compare V2 puts it below.
  export let table_location: "above" | "below" = "above"

  // Axis scaling mode.
  //
  // Full Scale is the default, and it is the honest one: these axes are bounded
  // scores - a pass rate over 0-1, a rating over 1-5 - so the score's own range
  // is a real range, and where a config sits in it is a fact about the config.
  // Relative min-max normalizes each axis across whatever happens to be pinned,
  // which turns a 0.02 spread into a full-radius swing: dramatic, and about
  // nothing. It stays one click away for the reader who wants that magnified
  // view of where configs differ.
  //
  // The consequence is accepted rather than designed around: run configs that
  // all score near 1.0 draw a near-perfect circle with little to tell apart.
  // They ARE that similar, and a chart that quietly switched modes to make them
  // look different would be inventing the difference.
  //
  // One mechanism, not two. This used to start relative and get flipped to
  // absolute by a reactive statement whenever a single config was plotted -
  // which is the same default, arrived at conditionally, and it meant pinning a
  // second config silently changed the scale under a reader who had not touched
  // the control.
  let absoluteScale = true

  function setScale(useAbsolute: boolean) {
    absoluteScale = useAbsolute
  }

  // Fallback full-scale max when we don't know the score's type. Most eval scores are
  // normalized to 0-1, and we only use it when the data actually fits under it.
  const DEFAULT_ABSOLUTE_MAX = 1

  // Above this many scores the tooltip lists only the weakest ones - the full set is
  // in the comparison table above.
  const MAX_TOOLTIP_SCORES = 10

  // Below this many axes there's no shape to read, so there's no chart to draw
  const MIN_RADAR_AXES = 3

  // One run config's polygon. `name` is what the reader sees and what echarts
  // keys the shape by; `configId` is what anything looking the config back up
  // should use, since a name is a fallback chain two configs can share.
  type RadarSeriesEntry = {
    value: (number | null)[]
    name: string
    configId: string | null
  }

  $: SCALE_TOOLTIP = `**Full Scale** (the default): each axis uses the score's own range - 0-1 for pass/fail, 1-5 for 5-star - so the shape is where these run configs actually stand. Run configs that all score near the top draw a near-perfect circle, which is what being that similar looks like.

**Relative**: each axis is scaled to the highest value across the selected run configs, magnifying whatever difference there is. Good for spotting where they differ, as long as you remember a full-radius swing may be worth 0.02.

Cost, latency and token axes score each run config against the others, so they stay relative in both modes. With a single run config there's nothing to compare against and they all sit at the midpoint. Hide one with the x on its row in the table ${table_location}.`

  // Only true once the task actually groups its criteria, so an ungrouped chart
  // is never told about a division it does not draw
  $: scaleTooltip = showFamilyKey
    ? `${SCALE_TOOLTIP}

Related criteria sit together: the axes are grouped into the families the task's specs declare, read **clockwise from the top**. Each family is named on the ring, over the arc that marks how far it runs.`
    : SCALE_TOOLTIP

  // Chart instance
  let chartInstance: echarts.ECharts | null = null

  // Which axis the pointer is nearest. echarts' radar tooltip is per-series - its
  // formatTooltip() is handed a dataIndex and maps over every indicator - so the
  // hovered axis has to be worked out from the pointer instead.
  let hoveredAxisIndex: number | null = null

  type RadarCoordSys = {
    cx: number
    cy: number
    getIndicatorAxes: () => { angle: number }[]
  }

  // getModel() is private in echarts' typings, and the radar's coordinate system is
  // the only place its centre and axis angles are exposed. Kept behind one cast and
  // fully guarded, so a change in echarts degrades to the whole-config tooltip
  // rather than throwing.
  function radarCoordSys(): RadarCoordSys | null {
    if (!chartInstance) return null
    const chart = chartInstance as unknown as {
      getModel?: () => {
        getComponent?: (
          mainType: string,
        ) => { coordinateSystem?: RadarCoordSys } | undefined
      }
    }
    const coordSys = chart
      .getModel?.()
      ?.getComponent?.("radar")?.coordinateSystem
    if (!coordSys || typeof coordSys.cx !== "number") return null
    if (typeof coordSys.getIndicatorAxes !== "function") return null
    return coordSys
  }

  // Which axis the pointer is on, from the pointer's own angle around the
  // radar centre - see nearest_axis_index. The hovered symbol's __dimIdx is
  // deliberately NOT preferred any more: every zero score draws its symbol AT
  // the centre and a near-zero one within a symbol's width of it, so the dot
  // under the pointer there is whichever of the stacked dots was drawn last,
  // and its axis can be anywhere on the ring - hovering a bottom-left point
  // could pop the tooltip of an axis whose name sits on the right. The
  // pointer's ray cannot fail that way: a symbol always sits ON its own axis,
  // so wherever the dots are readable the two agree. The tag is kept only for
  // the case where echarts' internals have changed shape and the geometry
  // cannot be read at all.
  function axisIndexFromPointer(event: {
    target?: { __dimIdx?: number }
    offsetX?: number
    offsetY?: number
  }): number | null {
    const tagged = event.target?.__dimIdx
    const taggedIndex = typeof tagged === "number" ? tagged : null

    const coordSys = radarCoordSys()
    if (
      !coordSys ||
      event.offsetX === undefined ||
      event.offsetY === undefined
    ) {
      return taggedIndex
    }
    const axes = coordSys.getIndicatorAxes()
    if (!axes?.length) return taggedIndex

    return nearest_axis_index(
      { x: event.offsetX, y: event.offsetY },
      { x: coordSys.cx, y: coordSys.cy },
      axes.map((axis) => axis.angle),
    )
  }

  // Indicator 0 sits at the top and the ring is read clockwise from there.
  // echarts walks indicators COUNTERCLOCKWISE from startAngle and has no
  // clockwise mode at all (its radar source carries a literal "TODO clockwise";
  // a `clockwise` option is silently ignored) - so the indicators and every
  // series' values are handed to echarts in ring-reversed order instead, which
  // renders echarts' counterclockwise walk as the clockwise reading order every
  // hand-drawn layer here (axis names, family arcs) is laid out in. See
  // ringReversed - one involution owns the correspondence both ways.
  const RADAR_START_ANGLE = 90

  // Reverse the direction a ring is walked while keeping index 0 at the top:
  // position j on the reversed ring holds item (n - j) % n. Applying it twice
  // is the identity, so the same function maps an echarts axis index back to
  // ours (see the tooltip formatter).
  function ringReversed<T>(items: T[]): T[] {
    return items.map((_, j) => items[(items.length - j) % items.length])
  }

  // The family band: a thin arc outside the ring, broken at each boundary, with
  // the family's name written along it. Same geometry, same tone ladder and the
  // same reasoning as the metrics radar - see compare_metrics_radar_chart and
  // $lib/utils/evolution/family_bands, which both charts share so they cannot
  // come out looking like two different conventions.
  const BAND_RING_GAP = 5
  const BAND_THICKNESS = 4
  const BAND_LABEL_GAP = 1
  const BAND_ARC_GAP = 16
  const FAMILY_LABEL_LINE_HEIGHT = 15
  const FAMILY_LABEL_FONT_SIZE = 13
  // One weight for every family name, not its own arc's tone - see the metrics
  // radar for why: the lightest rung would take the heading at twelve o'clock
  // down with it.
  const FAMILY_LABEL_COLOR = "#4b5563"
  const FAMILY_LABEL_BOLD_WIDTH = 1.05
  const FAMILY_LABEL_TAIL_GAP = 3
  // How far out the band and the family names reach
  const FAMILY_BLOCK_PX =
    BAND_RING_GAP + BAND_THICKNESS + BAND_LABEL_GAP + FAMILY_LABEL_LINE_HEIGHT
  // Centre of the family name's line, measured from the ring
  const FAMILY_LABEL_OFFSET = FAMILY_BLOCK_PX - FAMILY_LABEL_LINE_HEIGHT / 2

  const COST_KEY = "cost::mean_cost"
  const LATENCY_KEY = "cost::mean_total_llm_latency_ms"

  // Cost, latency and token counts are lower-is-better raw quantities with no
  // absolute range, so they're scored by position within the selected run configs
  // (metricToScore) on a shared 0-100 axis. That's a comparison, which means these
  // axes only carry information when there are at least two configs to compare - and
  // it's why they stay relative even in Full Scale mode.
  //
  // On the chart they're named for the direction that's better, since a bigger value
  // means less cost / less time / fewer tokens.
  const USAGE_LABELS: Record<string, string> = {
    [COST_KEY]: "Cost Efficiency",
    [LATENCY_KEY]: "Speed",
    "cost::mean_total_tokens": "Token Efficiency",
    "cost::mean_input_tokens": "Input Token Efficiency",
    "cost::mean_output_tokens": "Output Token Efficiency",
  }

  function isLowerIsBetterMetric(key: string): boolean {
    return key.startsWith("cost::")
  }

  // Position of a lower-is-better value within the selected configs, as a 0-100
  // score, lives in $lib/utils/relative_metric_score - the metrics radar scores
  // its axes with the same function, so "better" means one thing in both charts.

  // Eval score keys (the cost section is excluded - its metrics come back as usage
  // axes below, on their own terms)
  $: dataKeys = comparisonFeatures
    .filter((f) => f.eval_id !== "kiln_cost_section")
    .flatMap((f) => f.items.map((item) => item.key))

  // Usage axes come from the cost section of the table, so hiding a row there with
  // its x removes the axis here too - one control, where the numbers are.
  $: visibleUsageKeys = comparisonFeatures
    .filter((f) => f.eval_id === "kiln_cost_section")
    .flatMap((f) => f.items.map((item) => item.key))

  // A radar reads "further from center is better". Scores that don't share that
  // grammar are left off rather than drawn backwards: a lower-is-better score would
  // put its best result closest to the center, and an informational score has no
  // better end at all. Both stay in the table and the metric correlation chart.
  $: excludedKeys = dataKeys.filter(
    (key) =>
      scoreDirections[key] === "lower_is_better" ||
      scoreDirections[key] === "informational",
  )
  $: chartKeys = dataKeys.filter((key) => !excludedKeys.includes(key))

  $: notShownNote = (() => {
    const parts: string[] = []
    if (excludedKeys.length > 0) {
      parts.push(
        `${excludedKeys.length} lower-is-better or informational ${
          excludedKeys.length === 1 ? "score" : "scores"
        }`,
      )
    }
    if (noResultAxisCount > 0) {
      parts.push(
        `${noResultAxisCount} ${
          noResultAxisCount === 1 ? "score" : "scores"
        } without results for every selected run config`,
      )
    }
    if (parts.length === 0) return null
    return `Not shown: ${parts.join(", ")}. See the table ${table_location}.`
  })()

  // Get labels for radar indicators
  function getKeyLabel(dataKey: string): string {
    if (USAGE_LABELS[dataKey]) return USAGE_LABELS[dataKey]
    for (const feature of comparisonFeatures) {
      const item = feature.items.find((i) => i.key === dataKey)
      if (item) return item.label
    }
    return dataKey
  }

  // The eval a score belongs to, which is what carries its name and its spec
  function featureFor(dataKey: string): ComparisonFeature | undefined {
    return comparisonFeatures.find((feature) =>
      feature.items.some((item) => item.key === dataKey),
    )
  }

  // What an axis measures, for the popup on its name. Null when there is
  // nothing to say that the label is not already saying.
  //
  // The label is drawn wrapped and, on a crowded ring, ellipsized, so the
  // popup is built from the FULL name rather than from the text on screen -
  // seeing what a truncated one says in full is half of what it is for.
  //
  // The usage axes the older compare page appends are left out on purpose:
  // they are the performance track's business, and Compare V2 plots them on
  // the metrics ring, where the metric catalog explains them properly.
  function axisHelpHtml(dataKey: string): string | null {
    if (isLowerIsBetterMetric(dataKey)) return null
    const feature = featureFor(dataKey)
    const help = quality_axis_help(
      getKeyLabel(dataKey),
      feature?.category,
      feature ? specDescriptions[feature.eval_id] : null,
      // The score's own direction, so the popup states which way the axis
      // reads. A key with no entry is drawn as higher-is-better here, and
      // quality_axis_direction reports that same default rather than a second
      // opinion about it.
      scoreDirections[dataKey],
    )
    return help ? axis_help_html(help) : null
  }

  // Axis names are drawn just outside the outermost ring, where the left and
  // right ones run straight into the chart's edge. Side mode leaves that to
  // echarts (a fixed name width plus overflow: "break"); bottom mode places
  // them itself - see bottomAxisLabels below.
  //
  // One scrolling legend row: the name line (lineHeight 16) over up to three
  // {sub} lines (lineHeight 14), plus echarts' 5px legend padding either side.
  const BOTTOM_LEGEND_PX = 16 + 3 * 14 + 10
  // What the ring leaves under itself when the page carries the legend
  // instead: enough that a bottom axis name is not flush against the card's
  // edge, and nothing more - the room the legend used to take goes to radius.
  const EXTERNAL_LEGEND_PX = 8

  // How much of the box is reserved below the ring, either way
  $: reservedLegendPx = external_legend ? EXTERNAL_LEGEND_PX : BOTTOM_LEGEND_PX

  // ---------------------------------------------------------------------
  // Bottom-mode axis labels
  //
  // echarts centres each indicator name on its axis tip and stops there - the
  // radar component has no label de-cluttering of any kind. Vertical spacing
  // between neighbouring axes goes to zero as an axis approaches a pole, so
  // past ~20 axes (29 of them sit 12.4 deg apart) the names at the top and
  // bottom print straight through each other. Bottom mode therefore turns
  // echarts' names off and draws them as `graphic` text, placed by
  // bottomAxisLabels().
  //
  // The placement invariant is the one a reader assumes: every drawn name
  // sits ON its own axis ray. Crowding near a pole is resolved by pushing a
  // name OUTWARD along its ray - the one direction that keeps the invariant -
  // and a name whose ray has no clear room inside the card is hidden rather
  // than drawn beside an axis it does not belong to (the axis tooltip still
  // carries it). The geometry lives in place_labels_on_rays in
  // $lib/utils/evolution/metric_axes, where it is tested; the history of why
  // vertical packing was abandoned is on its block comment.
  //
  // A label cannot overlap a FAMILY name either: the family tier is an
  // annulus just inside these names, and every box is held outside the tier's
  // outer circle - see family_label_reach and axis_label_clearing_radius.
  // ---------------------------------------------------------------------

  const LABEL_FONT_SIZE = 11
  const LABEL_LINE_HEIGHT = 14
  const LABEL_COLOR = "#666"
  // What a name is wrapped to, in px - the same ~13 characters the metrics
  // radar wraps to, so the two rings carry names of the same shape. Fixed
  // rather than "whatever is left outside the ring", which is what it used to
  // be: that made the wrap width a function of the radius and the radius a
  // function of the wrap width, and the knot was cut by pricing EVERY name as
  // though it were the widest one pointing due east. See radarLayout.
  const LABEL_WRAP_BUDGET_PX = 78
  // The most lines a name may take. Fewer are used when the ring is crowded -
  // see wrapAxisNames, which walks down from here until the labels fit the
  // band. Two rather than three, because a taller name costs radius twice: it
  // reaches further up and down the box, and it pushes every axis name outwards
  // through axisLabelGapFor. Longer names are ellipsized; the axis tooltip
  // always carries the full one.
  const LABEL_MAX_LINES = 2
  // Clear space between two stacked labels
  const LABEL_GAP_Y = 5
  // From the outer ring to the nearest edge of the text
  const LABEL_RING_GAP = 12
  // Keep text off the container's left and right edges...
  const LABEL_EDGE_PAD = 8
  // ...and off the top of the box and the legend underneath
  const LABEL_BAND_PAD = 2

  type BottomAxisLabel = {
    index: number
    text: string
    x: number
    y: number
    align: "left" | "right" | "center"
    width: number
    height: number
  }

  // Rough advance widths for the UI's sans-serif stack, as a fraction of the
  // font size. This only picks wrap points and keeps text off the container's
  // edge - labels are held apart by the layout, not by this estimate - so a few
  // percent of error costs nothing, and it is deterministic, which measuring
  // against whichever font actually loaded is not.
  const WIDE_GLYPHS = /[MWmw@%]/
  const NARROW_GLYPHS = /[ijlt.,;:'`!|()[\]/\\ ]/

  function estimateTextWidth(
    text: string,
    fontSize: number = LABEL_FONT_SIZE,
  ): number {
    let width = 0
    for (const glyph of text) {
      if (WIDE_GLYPHS.test(glyph)) {
        width += fontSize * 0.92
      } else if (NARROW_GLYPHS.test(glyph)) {
        width += fontSize * 0.31
      } else if (glyph >= "A" && glyph <= "Z") {
        width += fontSize * 0.7
      } else {
        width += fontSize * 0.55
      }
    }
    return width
  }

  function ellipsize(text: string, budget: number): string {
    if (estimateTextWidth(text) <= budget) return text
    let kept = text.replace(/…$/, "")
    while (kept.length > 0 && estimateTextWidth(`${kept}…`) > budget) {
      kept = kept.slice(0, -1)
    }
    return `${kept}…`
  }

  // Greedy word wrap to a px budget. Every line comes back inside the budget: a
  // single word too wide for it is ellipsized rather than left to run off the
  // edge, and so is the last line when a name needs more than maxLines.
  function wrapToWidth(
    name: string,
    budget: number,
    maxLines: number,
  ): string[] {
    const lines: string[] = []
    let line = ""
    for (const word of name.split(/\s+/).filter((part) => part.length > 0)) {
      if (line.length === 0) {
        line = word
      } else if (estimateTextWidth(`${line} ${word}`) <= budget) {
        line = `${line} ${word}`
      } else {
        lines.push(line)
        line = word
      }
    }
    if (line.length > 0) lines.push(line)
    if (lines.length === 0) return [""]
    if (lines.length > maxLines) {
      lines.length = maxLines
      lines[maxLines - 1] = `${lines[maxLines - 1]}…`
    }
    return lines.map((entry) => ellipsize(entry, budget))
  }

  // Where OUR axis i sits: at startAngle, walking the way the ring is read
  // (clockwise), so the angle DECREASES with the index. echarts itself walks
  // the other way - ringReversed is what makes its layout land on these same
  // rays. Radians, y up, the convention radarCoordSys(), the radar's own
  // dataToPoint and $lib/utils/evolution/metric_axes all share.
  function axisAngles(count: number): number[] {
    return Array.from(
      { length: count },
      (_, index) =>
        (RADAR_START_ANGLE * Math.PI) / 180 - (index * Math.PI * 2) / count,
    )
  }

  // Every name wrapped, at the most lines the ring can hold.
  //
  // Wrapped BEFORE the radius is solved, which is the point: fit_radar needs the
  // boxes, and how many lines fit depends only on how many names crowd one side
  // of the ring - a count, not a radius. So the knot the old radius-dependent
  // wrap width tied does not have to be tied at all. Two lines while there is
  // room for them, one when there is not, and past that the stride in
  // bottomAxisLabels starts hiding names.
  function wrapAxisNames(
    names: string[],
    band: number,
    lineCap: number = LABEL_MAX_LINES,
  ): string[][] {
    // Half the ring, rounded up: the crowded side is the one that has to fit
    const perSide = Math.ceil(names.length / 2)
    for (let maxLines = lineCap; maxLines > 1; maxLines--) {
      const wrapped = names.map((name) =>
        wrapToWidth(name, LABEL_WRAP_BUDGET_PX, maxLines),
      )
      const tallest = Math.max(1, ...wrapped.map((lines) => lines.length))
      if (perSide * (tallest * LABEL_LINE_HEIGHT + LABEL_GAP_Y) <= band) {
        return wrapped
      }
    }
    return names.map((name) => wrapToWidth(name, LABEL_WRAP_BUDGET_PX, 1))
  }

  // The wrapped names as boxes at the angles echarts would lay them out at,
  // which is what fit_radar solves the radius against.
  function axisLabelBoxes(wrapped: string[][]): RadarAxisLabel[] {
    const angles = axisAngles(wrapped.length)
    return wrapped.map((lines, index) => ({
      angle: angles[index],
      width: Math.max(...lines.map((line) => estimateTextWidth(line))),
      height: lines.length * LABEL_LINE_HEIGHT,
    }))
  }

  // Where each axis name goes in bottom mode, in canvas px. `y` is the vertical
  // centre of the text block and `x` the edge it is anchored by, which is what
  // echarts' graphic text wants alongside align/verticalAlign. The geometry is
  // place_labels_on_rays': every drawn name sits ON its own axis ray, crowding
  // pushes a name outward along that ray, and a name whose ray has no clear
  // room inside the card comes back absent - hidden, not misplaced.
  function bottomAxisLabels(
    wrapped: string[][],
    box: {
      cx: number
      cy: number
      /** Ring to the anchor of a name, including the family band and its names */
      labelGap: number
      radius: number
      width: number
      bandBottom: number
      /** No name's box may come inside this - the family tier. 0 when ungrouped */
      keepOut: number
    },
  ): BottomAxisLabel[] {
    const count = wrapped.length
    if (count === 0) return []
    const angles = axisAngles(count)
    const sizes = wrapped.map((lines) => ({
      width: Math.max(...lines.map((line) => estimateTextWidth(line))),
      height: lines.length * LABEL_LINE_HEIGHT,
    }))
    const placements = place_labels_on_rays(
      wrapped.map((lines, index) => ({
        index,
        angle: angles[index],
        width: sizes[index].width,
        height: sizes[index].height,
      })),
      {
        cx: box.cx,
        cy: box.cy,
        minRadius: box.radius + box.labelGap,
        keepOut: box.keepOut,
        bandTop: LABEL_BAND_PAD,
        bandBottom: box.bandBottom - LABEL_BAND_PAD,
        width: box.width,
        edgePad: LABEL_EDGE_PAD,
        gap: LABEL_GAP_Y,
      },
    )
    return placements.map((placement) => ({
      index: placement.index,
      text: wrapped[placement.index].join("\n"),
      x: placement.x,
      y: placement.y,
      align: placement.align,
      width: sizes[placement.index].width,
      height: sizes[placement.index].height,
    }))
  }

  // The measured box, rounded and thresholded so dragging a window edge
  // doesn't re-issue setOption for every sub-pixel step. Only tracked in
  // bottom mode: side mode's geometry is fixed percentages, so re-drawing it
  // on resize would buy nothing and would reset the legend's selection.
  let chartWidth = 0
  let chartHeight = 0

  function recordChartSize(node: HTMLElement) {
    if (legend_position !== "bottom") return
    const width = Math.round(node.clientWidth)
    const height = Math.round(node.clientHeight)
    if (
      Math.abs(width - chartWidth) < 8 &&
      Math.abs(height - chartHeight) < 8
    ) {
      return
    }
    chartWidth = width
    chartHeight = height
  }

  // Get simple display name for the series (used as the internal name/key).
  // The page's label wins when it supplies one, so a series is called the same
  // thing here as on the charts beside it and in the legend above them.
  function getSeriesDisplayName(config: TaskRunConfig): string {
    const assigned = config.id ? seriesLabels[config.id] : undefined
    return assigned ?? series_label(config, model_info)
  }

  // The raw quantity behind a usage axis, in its own units
  function formatUsageValue(key: string, value: number | null): string {
    if (value === null) return "N/A"
    if (key === COST_KEY) return `$${value.toFixed(6)}`
    if (key === LATENCY_KEY) return formatLatency(value)
    return `${Math.round(value).toLocaleString()} tokens`
  }

  // Mean usage for a config, formatted for display. Null when unavailable.
  function getUsageSummary(config: TaskRunConfig | undefined): {
    cost: string | null
    latency: string | null
    totalTokens: string | null
  } {
    const raw = (key: string) =>
      config?.id ? getModelValueRaw(config.id, key) : null
    const meanCost = raw(COST_KEY)
    const meanLatency = raw(LATENCY_KEY)
    const meanTotalTokens = raw("cost::mean_total_tokens")
    return {
      cost: meanCost === null ? null : formatUsageValue(COST_KEY, meanCost),
      latency:
        meanLatency === null
          ? null
          : formatUsageValue(LATENCY_KEY, meanLatency),
      totalTokens:
        meanTotalTokens === null
          ? null
          : formatUsageValue("cost::mean_total_tokens", meanTotalTokens),
    }
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

  function buildLegendFormatter(): Record<string, string> {
    const formatter: Record<string, string> = {}
    for (const configId of selectedRunConfigIds) {
      const config = run_configs.find((c) => c.id === configId)
      if (!config) continue
      const displayName = getSeriesDisplayName(config)
      formatter[displayName] = `${displayName}\n${buildLegendSubtext(config)}`
    }
    return formatter
  }

  // A run config's colour, decided by the page when it supplies a map (see
  // series_color_map) and otherwise taken from the palette by data-item order,
  // which is what this chart did for everybody. The page's map is what keeps a
  // config the same colour here and on the two charts beside it: a config with
  // no result for the shared axes is dropped from `plottedConfigs`, and used to
  // renumber the palette for every config after it.
  function seriesColorFor(
    runConfigId: string | null | undefined,
    index: number,
  ): string {
    const assigned = runConfigId ? seriesColors[runConfigId] : undefined
    if (assigned) return assigned
    const palette = chartInstance?.getOption()?.color as string[] | undefined
    if (!palette?.length) return FALLBACK_SERIES_COLOR
    return palette[index % palette.length]
  }

  function tooltipMarker(color: string): string {
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};margin-right:6px;"></span>`
  }

  // One metric across every plotted run config, so hovering a point answers "how do
  // they compare here" rather than reciting everything this config scored.
  function buildAxisTooltip(
    axisIndex: number,
    keys: string[],
    series: RadarSeriesEntry[],
    hoveredName: string,
  ): string {
    const key = keys[axisIndex]
    const isUsage = isLowerIsBetterMetric(key)

    let html = `<div style="font-weight: bold; margin-bottom: 6px;">${getKeyLabel(key)}</div>`
    series.forEach((entry, index) => {
      const plotted = entry.value[axisIndex]
      // By id rather than by matching the display name back to a config: the
      // name is a fallback chain and two configs may land on the same one.
      const rawValue = entry.configId
        ? getModelValueRaw(entry.configId, key)
        : null

      let shown: string
      if (plotted === null || rawValue === null) {
        shown = "N/A"
      } else if (isUsage) {
        // The axis plots a relative score, so give the quantity behind it too
        shown = `${plotted.toFixed(1)} <span style="color: #888;">(${formatUsageValue(key, rawValue)})</span>`
      } else {
        shown = rawValue.toFixed(3)
      }

      const weight = entry.name === hoveredName ? "600" : "400"
      html += `<div style="font-weight: ${weight};">${tooltipMarker(
        seriesColorFor(entry.configId, index),
      )}${entry.name}: ${shown}</div>`
    })
    return html
  }

  // Build full tooltip HTML for a run config (reused by chart tooltip and legend tooltip)
  function buildRunConfigTooltip(
    name: string,
    axisMaxes: Record<string, number>,
    keys: string[],
  ): string {
    const config = run_configs.find((c) => getSeriesDisplayName(c) === name)

    let html = `<div style="font-weight: bold; margin-bottom: 4px;">${name}</div>`
    if (config && isMcpRunConfig(config.run_config_properties)) {
      const toolName =
        config.run_config_properties.tool_reference.tool_name ?? "MCP Tool"
      html += `<div>MCP Tool: ${toolName}</div>`
    } else {
      const modelName = config
        ? getRunConfigModelDisplayName(config, model_info) || "Unknown"
        : "Unknown"
      const promptName = config
        ? getRunConfigPromptDisplayName(config, prompts)
        : null
      html += `<div>Model: ${modelName}</div>`
      if (promptName) {
        html += `<div>Prompt: ${promptName}</div>`
      }
      if (config) {
        const transformLabel = getRunConfigInputTransformSummaryLabel(config)
        if (transformLabel) {
          html += `<div>Input Transform: ${transformLabel}</div>`
        }
      }
    }

    const usage = getUsageSummary(config)
    if (usage.cost) html += `<div>Mean Cost: ${usage.cost}</div>`
    if (usage.latency) html += `<div>Mean Latency: ${usage.latency}</div>`
    if (usage.totalTokens) {
      html += `<div>Mean Total Tokens: ${usage.totalTokens}</div>`
    }

    // Eval scores only. The usage axes plot a relative score rather than their raw
    // quantity, so ranking them against pass rates would compare unlike things -
    // their real values are listed above instead.
    const scores = keys
      .filter((key) => !isLowerIsBetterMetric(key))
      .map((key) => {
        const value = config?.id ? getModelValueRaw(config.id, key) : null
        const max = axisMaxes[key] || 1
        return {
          label: getKeyLabel(key),
          value,
          // Rank by position on the axis, so scores with different ranges (0-1 vs
          // 1-5) are comparable. Missing values sort first: "didn't run" is worth
          // surfacing.
          position: value === null ? -1 : value / max,
        }
      })

    const trimmed = scores.length > MAX_TOOLTIP_SCORES
    const shown = trimmed
      ? [...scores]
          .sort((a, b) => a.position - b.position)
          .slice(0, MAX_TOOLTIP_SCORES)
      : scores

    html += `<div style="font-weight: bold; margin-bottom: 4px; padding-top: 8px;">${
      trimmed ? "Lowest Scores" : "Values"
    }</div>`
    for (const score of shown) {
      const formatted = score.value === null ? "N/A" : score.value.toFixed(3)
      html += `<div>${score.label}: ${formatted}</div>`
    }
    if (trimmed) {
      html += `<div style="color: #888; padding-top: 4px;">+${
        scores.length - shown.length
      } more in the table ${table_location}</div>`
    }

    return html
  }

  // Axis max in "Full Scale" mode: the score's own range when we know it, otherwise
  // the normalized 0-1 default. Never returns a max below the data, so nothing is
  // clipped for unbounded (custom) scores or unrecognized score types.
  function absoluteAxisMax(
    key: string,
    rawMax: number,
    paddedMax: number,
  ): number {
    const knownMax = scoreAxisMaxes[key]
    if (knownMax !== undefined && knownMax >= rawMax) {
      return knownMax
    }
    return rawMax <= DEFAULT_ABSOLUTE_MAX ? DEFAULT_ABSOLUTE_MAX : paddedMax
  }

  function generateChartData(): {
    indicators: { name: string; max: number }[]
    series: RadarSeriesEntry[]
    legend: string[]
    axisMaxes: Record<string, number>
    keys: string[]
    noResultKeyCount: number
  } {
    const indicators: { name: string; max: number }[] = []
    const series: RadarSeriesEntry[] = []
    const legend: string[] = []
    const axisMaxes: Record<string, number> = {}
    const empty = {
      indicators,
      series,
      legend,
      axisMaxes,
      keys: [] as string[],
    }

    if (chartKeys.length === 0 || selectedRunConfigIds.length === 0) {
      return { ...empty, noResultKeyCount: 0 }
    }

    // Run configs with at least one result. One with nothing to plot is left out
    // entirely rather than emptying every axis.
    const plottedConfigs = selectedRunConfigIds
      .map((configId) => run_configs.find((c) => c.id === configId))
      .filter((config): config is TaskRunConfig => !!config)
      .filter((config) =>
        chartKeys.some(
          (key) => getModelValueRaw(config.id ?? null, key) !== null,
        ),
      )

    const candidateKeys = [...chartKeys, ...visibleUsageKeys]

    // Only scores every plotted config has a result for. ECharts draws a missing
    // radar value at the center of the chart (radarLayout's getValueMissingPoint),
    // which is indistinguishable from scoring zero - so an axis one config hasn't
    // been evaluated on can't be drawn honestly at all. It's left out, and counted
    // under the chart title instead.
    const keys = candidateKeys.filter((key) =>
      plottedConfigs.every(
        (config) => getModelValueRaw(config.id ?? null, key) !== null,
      ),
    )
    const noResultKeyCount = candidateKeys.length - keys.length

    if (keys.length < MIN_RADAR_AXES) {
      return { ...empty, noResultKeyCount }
    }

    // Every value on a usage axis, so each can be scored by its position among them
    const usageValues: Record<string, number[]> = {}
    for (const key of keys) {
      if (!isLowerIsBetterMetric(key)) continue
      usageValues[key] = plottedConfigs
        .map((config) => getModelValueRaw(config.id ?? null, key))
        .filter((value): value is number => value !== null)
    }

    // Calculate max values for each data key across the plotted run configs
    for (const key of keys) {
      if (isLowerIsBetterMetric(key)) {
        // Already a 0-100 score, in both scale modes
        axisMaxes[key] = 100
        continue
      }
      let max = 0
      for (const config of plottedConfigs) {
        const value = getModelValueRaw(config.id ?? null, key)
        if (value !== null && value > max) {
          max = value
        }
      }
      // Add 10% padding to max for better visualization
      const paddedMax = max > 0 ? max * 1.1 : 1
      axisMaxes[key] = absoluteScale
        ? absoluteAxisMax(key, max, paddedMax)
        : paddedMax
    }

    for (const key of keys) {
      indicators.push({
        name: getKeyLabel(key),
        max: axisMaxes[key],
      })
    }

    // Build series data for each plotted run config. Every one of them has a value
    // for every key by construction above.
    for (const config of plottedConfigs) {
      const values = keys.map((key) => {
        const rawValue = getModelValueRaw(config.id ?? null, key)
        if (rawValue === null) return null
        return isLowerIsBetterMetric(key)
          ? relative_metric_score(rawValue, usageValues[key] || [])
          : rawValue
      })
      const name = getSeriesDisplayName(config)
      legend.push(name)
      series.push({ value: values, name, configId: config.id ?? null })
    }

    return { indicators, series, legend, axisMaxes, keys, noResultKeyCount }
  }

  // Check if there's data to display (reactive - references every input that can
  // change what generateChartData() returns)
  $: chartSummary = (() => {
    // visibleUsageKeys is referenced so this re-runs when a usage row is hidden
    if (
      !chartKeys ||
      chartKeys.length === 0 ||
      !selectedRunConfigIds ||
      !visibleUsageKeys
    ) {
      return { hasData: false, noResultKeyCount: 0, keys: [] as string[] }
    }
    const { indicators, series, noResultKeyCount, keys } = generateChartData()
    return {
      hasData: indicators.length > 0 && series.length > 0,
      noResultKeyCount,
      keys,
    }
  })()
  $: hasData = chartSummary.hasData
  $: noResultAxisCount = chartSummary.noResultKeyCount

  // The family runs as they will actually be drawn. Derived from the keys that
  // survived every filter, not from what the page offered, so a score dropped
  // for having no result on some config takes its share of the arc with it, a
  // family emptied that way leaves neither an orphaned arc nor a name in the
  // key, and the arcs and the key can never disagree.
  //
  // A key with no family - the usage axes the old compare page appends, or an
  // eval the task's scheme missed - falls into one shared "Other" run. With no
  // families at all every key lands there, that is a single run, and
  // family_bands returns nothing: the no-grouping case needs no flag of its own.
  $: familyBands =
    legend_position === "bottom" && hasData
      ? family_bands(
          chartSummary.keys.map((key) => ({
            family: axisFamilies[key]?.id ?? "__other__",
            label: axisFamilies[key]?.label ?? "Other",
          })),
        )
      : ([] as FamilyBand[])

  $: showFamilyKey = hasData && familyBands.length > 0

  // How far out an axis name is anchored.
  //
  // A grouped ring holds its names off past the band AND past the family name -
  // and then past half an axis name on top, because a name is centred on its
  // anchor and laid out sideways, so its inner half reaches back towards the
  // ring. Without that half the family name lands underneath its own family's
  // axis names, which is exactly where a family with an odd number of axes puts
  // it: the midpoint of the arc IS an axis.
  //
  // Measured from the names as wrapped rather than assumed to be the worst
  // case, so a ring of one-line names does not pay for a second line. An
  // ungrouped chart pays for none of it and keeps every pixel of radius it had
  // before families existed.
  function axisLabelGapFor(wrapped: string[][]): number {
    if (familyBands.length === 0) return LABEL_RING_GAP
    const tallest = Math.max(
      0,
      ...wrapped.map((lines) => lines.length * LABEL_LINE_HEIGHT),
    )
    return FAMILY_BLOCK_PX + FAMILY_LABEL_TAIL_GAP + tallest / 2
  }

  // When there's nothing to draw, say which of the two reasons it is
  $: noDataMessage =
    noResultAxisCount > 0
      ? `The selected run configurations share fewer than ${MIN_RADAR_AXES} scores with results. Run the missing evals, or compare fewer run configurations.`
      : "Create and run evals to see a comparison chart."

  function updateChart() {
    if (!chartInstance) return

    if (!hasData) {
      chartInstance.clear()
      return
    }

    const { indicators, series, legend, axisMaxes, keys } = generateChartData()

    const legendFormatter = buildLegendFormatter()

    // A couple of configs don't need a legend column - centering the radar and
    // dropping the legend underneath buys a much larger plot. legend_position
    // "bottom" asks for that arrangement whatever the series count.
    const forceBottomLegend = legend_position === "bottom"
    const compactLayout = forceBottomLegend || series.length <= 2

    // Bottom mode solves its own geometry and draws its own axis names. Both
    // wait for the box to be measured; until then the ring falls back to
    // percentages, and there is nothing on screen to label anyway.
    const measured = forceBottomLegend && chartWidth > 0 && chartHeight > 0
    const measureFamily = (value: string) =>
      estimateTextWidth(value, FAMILY_LABEL_FONT_SIZE) * FAMILY_LABEL_BOLD_WIDTH

    // The whole bottom-mode solve - wrap, radius, family tier, axis names -
    // for one wrap height, so it can be run again at another. The ring radius
    // is solved rather than a percentage of min(width, height): this card is
    // much taller than it is wide at every layout the page produces, and it is
    // solved against where the names will actually LAND rather than against
    // the widest name as though every axis pointed due east. See fit_radar.
    //
    // The family tier is solved BEFORE the axis names, because how far it
    // reaches is what the axis names have to stay clear of - and it is drawn
    // as graphics rather than by the radar: echarts splits a radar's
    // background into rings, never into sectors, and the arcs belong OUTSIDE
    // the plot where they cannot sit under the polygons. The glyph table
    // above is for regular weight and a family name is set semibold, so the
    // estimate is nudged up rather than left to run narrow into its budget.
    const solveBottomLayout = (lineCap: number) => {
      const wrappedNames = wrapAxisNames(
        indicators.map((indicator) => indicator.name),
        chartHeight - reservedLegendPx - 2 * LABEL_BAND_PAD,
        lineCap,
      )
      const labelGap = axisLabelGapFor(wrappedNames)
      const bottomFit = fit_radar(
        { width: chartWidth, height: chartHeight },
        axisLabelBoxes(wrappedNames),
        {
          legendHeight: reservedLegendPx,
          labelGap,
          pad: LABEL_EDGE_PAD,
        },
      )
      const familyPlacements = familyBands.map((band) =>
        family_band_label(band, keys.length, {
          startAngleDegrees: RADAR_START_ANGLE,
          cx: bottomFit.cx,
          cy: bottomFit.cy,
          radius: bottomFit.radius + FAMILY_LABEL_OFFSET,
        }),
      )
      // A name may spill into a neighbour's arc when the neighbour is not
      // using it, which is what keeps a one-axis family's heading from coming
      // out as "Data I…" beside a twelve-axis one with 600px of empty arc.
      const familyBudgets = family_label_budgets(
        familyBands.map((band) => measureFamily(band.label)),
        familyPlacements.map((placement) => placement.sweep),
        BAND_ARC_GAP,
      )
      const familyTexts = familyBands.map((band, index) =>
        truncate_to_width(band.label, familyBudgets[index], measureFamily),
      )
      // The circle no axis name may come inside. Measured from the names as
      // they will be DRAWN, so a heading cut down to its arc is priced at the
      // width it ends up with rather than the one it asked for.
      const familyKeepOut =
        family_label_reach(
          bottomFit.radius + FAMILY_LABEL_OFFSET,
          FAMILY_LABEL_LINE_HEIGHT,
          familyTexts.filter((text) => text.length > 0).map(measureFamily),
        ) + FAMILY_LABEL_TAIL_GAP
      const axisLabels = bottomAxisLabels(wrappedNames, {
        cx: bottomFit.cx,
        cy: bottomFit.cy,
        labelGap,
        radius: bottomFit.radius,
        width: chartWidth,
        bandBottom: chartHeight - reservedLegendPx,
        keepOut: familyBands.length > 0 ? familyKeepOut : 0,
      })
      return { bottomFit, familyPlacements, familyTexts, axisLabels }
    }

    // Prefer two-line names, but a name SHOWN beats a name unabridged: when
    // the on-ray placement cannot give every two-line name clear room - near
    // the horizontal, a tall name can only escape a neighbour by running off
    // the card's edge - the one-line solve's shorter boxes usually can, since
    // packing room is exactly what the second line was costing. Take the
    // solve that draws the most names; two lines win ties, and what still
    // cannot fit stays discoverable in the axis and data-point tooltips.
    let bottomLayout = measured ? solveBottomLayout(LABEL_MAX_LINES) : null
    if (bottomLayout && bottomLayout.axisLabels.length < indicators.length) {
      const singleLine = solveBottomLayout(1)
      if (singleLine.axisLabels.length > bottomLayout.axisLabels.length) {
        bottomLayout = singleLine
      }
    }
    const bottomFit = bottomLayout ? bottomLayout.bottomFit : null
    const familyPlacements = bottomLayout ? bottomLayout.familyPlacements : []
    const familyTexts = bottomLayout ? bottomLayout.familyTexts : []
    const axisLabels = bottomLayout ? bottomLayout.axisLabels : []

    const bandGraphics =
      bottomFit && familyBands.length > 0
        ? familyBands.flatMap((band, index) => {
            const inner = bottomFit.radius + BAND_RING_GAP
            const outer = inner + BAND_THICKNESS
            const arc = family_band_arc(band, keys.length, {
              startAngleDegrees: RADAR_START_ANGLE,
              // A gap in px, as an angle at the radius it is drawn at, so the
              // boundary looks the same width whatever the card size
              gapRadians: BAND_ARC_GAP / outer,
            })
            const placement = familyPlacements[index]
            const text = familyTexts[index]
            return [
              {
                type: "sector" as const,
                // Inert: the tooltip works out which axis is under the cursor
                // from the pointer, and anything that could become the event
                // target first would break that - see axisIndexFromPointer.
                silent: true,
                z: 0,
                shape: {
                  cx: bottomFit.cx,
                  cy: bottomFit.cy,
                  r0: inner,
                  r: outer,
                  startAngle: arc.startAngle,
                  endAngle: arc.endAngle,
                  clockwise: true,
                  cornerRadius: BAND_THICKNESS / 2,
                },
                style: { fill: family_tone(index, familyBands.length) },
              },
              ...(text
                ? [
                    {
                      type: "text" as const,
                      silent: true,
                      z: 100,
                      x: placement.x,
                      y: placement.y,
                      rotation: placement.rotation,
                      style: {
                        text,
                        align: "center" as const,
                        verticalAlign: "middle" as const,
                        fontSize: FAMILY_LABEL_FONT_SIZE,
                        fontWeight: 600,
                        fill: FAMILY_LABEL_COLOR,
                      },
                    },
                  ]
                : []),
            ]
          })
        : []

    const legendTextStyle = {
      lineHeight: 16,
      rich: {
        sub: {
          fontSize: 11,
          color: "#666",
          lineHeight: 14,
        },
      },
    }

    chartInstance.setOption(
      {
        tooltip: {
          trigger: "item",
          confine: true,
          formatter: (params: { name: string }) => {
            // The legend keeps the whole-config summary; on the chart itself a
            // hovered point is a question about one metric.
            if (
              hoveredAxisIndex !== null &&
              hoveredAxisIndex >= 0 &&
              hoveredAxisIndex < keys.length
            ) {
              // hoveredAxisIndex is an echarts axis index; the ring is fed to
              // echarts ring-reversed, so map it back to ours before indexing
              // keys/series. ringReversed's involution, as an index map.
              const ourAxisIndex =
                (keys.length - hoveredAxisIndex) % keys.length
              return buildAxisTooltip(ourAxisIndex, keys, series, params.name)
            }
            return buildRunConfigTooltip(params.name, axisMaxes, keys)
          },
        },
        // The page can own the legend for a whole section of charts, in which
        // case this card draws none - see `external_legend`. Hiding a config
        // is then subtraction at the source: it never reaches
        // selectedRunConfigIds, so there is no per-chart selection state to
        // keep and none to get out of step with the charts beside it.
        legend: external_legend
          ? { show: false }
          : {
              data: legend,
              // Clicking a legend entry hides/shows that run config's polygon.
              // With this many overlapping shapes, isolating one is the only
              // way to read the chart - the legend is not a selection surface.
              selectedMode: true,
              formatter: (name: string) => legendFormatter[name] || name,
              tooltip: {
                show: true,
                formatter: (params: { name: string }) =>
                  buildRunConfigTooltip(params.name, axisMaxes, keys),
              },
              textStyle: legendTextStyle,
              ...(compactLayout
                ? {
                    orient: "horizontal" as const,
                    bottom: 0,
                    left: "center" as const,
                    itemGap: forceBottomLegend ? 24 : 40,
                    // Many configs in a narrow column would otherwise wrap into
                    // the plot; scroll mode keeps the legend to one paged row.
                    ...(forceBottomLegend ? { type: "scroll" as const } : {}),
                  }
                : {
                    orient: "vertical" as const,
                    left: "60%",
                    top: "middle" as const,
                    itemGap: 16,
                  }),
            },
        radar: {
          // Ring-reversed so echarts' counterclockwise walk renders as the
          // clockwise reading order - see RADAR_START_ANGLE / ringReversed.
          indicator: ringReversed(indicators),
          // Bottom mode fills its (tall, page-wide) box: the ring is centred in
          // what the legend leaves and grown until the axis names would leave
          // the box - see fit_radar. Side mode's percentages are unchanged, and
          // so is the unmeasured first paint.
          center: bottomFit
            ? [bottomFit.cx, bottomFit.cy]
            : forceBottomLegend
              ? ["50%", "45%"]
              : compactLayout
                ? ["50%", "46%"]
                : ["32%", "50%"],
          radius: bottomFit
            ? bottomFit.radius
            : forceBottomLegend
              ? "71%"
              : compactLayout
                ? "62%"
                : "85%",
          startAngle: RADAR_START_ANGLE,
          axisName: {
            color: LABEL_COLOR,
            ...(forceBottomLegend
              ? {
                  // Drawn as `graphic` text instead, so they can be
                  // de-cluttered - echarts has no way to do that itself.
                  show: false,
                }
              : {
                  fontSize: 12,
                  // Wrap long score names instead of letting neighbours collide
                  width: 110,
                  overflow: "break",
                  lineHeight: 14,
                }),
          },
          splitArea: {
            areaStyle: {
              color: ["#f8f9fa", "#ffffff"],
            },
          },
          splitLine: {
            lineStyle: {
              color: "#e5e7eb",
            },
          },
          axisLine: {
            lineStyle: {
              color: "#e5e7eb",
            },
          },
        },
        series: [
          {
            name: "Eval Scores",
            type: "radar",
            // Values permuted the same way as the indicators, so value j still
            // lands on the axis it belongs to.
            data: series.map((entry) => {
              // Stated per polygon when the page has decided the colours, and
              // left to echarts' palette otherwise. `configId` is ours, not
              // echarts', so it is dropped rather than passed through.
              const assigned = entry.configId
                ? seriesColors[entry.configId]
                : undefined
              return {
                name: entry.name,
                value: ringReversed(entry.value),
                ...(assigned
                  ? {
                      itemStyle: { color: assigned },
                      lineStyle: { color: assigned },
                      ...(series.length === 1
                        ? { areaStyle: { color: assigned, opacity: 0.2 } }
                        : {}),
                    }
                  : {}),
              }
            }),
            lineStyle: {
              width: 2,
            },
            symbolSize: 6,
            // Filling one shape makes it readable. Filling several makes mud.
            ...(series.length === 1 ? { areaStyle: { opacity: 0.2 } } : {}),
          },
        ],
        // Bottom mode's axis names, hand-placed - see bottomAxisLabels.
        //
        // A name with something to explain is the hover target for its own
        // popup, and is the one graphic here that is not silent. That is safe
        // because a name is always drawn outside the ring - bottomAxisLabels
        // floors every radius at the ring circle - so it can never sit over a
        // polygon and take the pointer off a data point. A name with nothing
        // to say stays inert, like the family arcs.
        ...(forceBottomLegend
          ? {
              graphic: {
                elements: [
                  // Family arcs first, so they sit under the labels they group
                  ...bandGraphics,
                  ...axisLabels.map((label) => {
                    const help = axisHelpHtml(keys[label.index])
                    return {
                      type: "text" as const,
                      x: label.x,
                      y: label.y,
                      silent: !help,
                      // Nothing to click, so nothing that says there is
                      cursor: "default",
                      z: 100,
                      // echarts' own tooltip, so hovering a name and hovering
                      // a point are two views of the same object rather than
                      // two popup styles
                      ...(help ? { tooltip: { formatter: () => help } } : {}),
                      style: {
                        text: label.text,
                        align: label.align,
                        verticalAlign: "middle" as const,
                        fontSize: LABEL_FONT_SIZE,
                        lineHeight: LABEL_LINE_HEIGHT,
                        fill: LABEL_COLOR,
                      },
                    }
                  }),
                ],
              },
            }
          : {}),
      },
      true,
    )
  }

  // Named so the reactive block below re-runs when the scaling mode is toggled
  $: axisScaleMode = absoluteScale ? "absolute" : "relative"

  // Same trick for the measured box, which bottom mode's geometry reads. Only
  // ever changes in bottom mode, so side mode still redraws on data alone.
  $: chartBoxKey = `${chartWidth}x${chartHeight}`

  // Update chart when data changes (model_info and prompts may load async). Every
  // input that changes what's drawn has to be referenced here, or the chart keeps
  // showing the previous render.
  $: if (
    chartInstance &&
    comparisonFeatures &&
    selectedRunConfigIds &&
    axisScaleMode &&
    chartBoxKey &&
    legend_position &&
    // A number, always truthy, and it moves when `external_legend` does - the
    // flag itself cannot go in an && chain, since `false` would stop the
    // redraw rather than trigger one
    reservedLegendPx &&
    seriesColors &&
    seriesLabels &&
    scoreAxisMaxes &&
    scoreDirections &&
    visibleUsageKeys &&
    axisFamilies &&
    specDescriptions &&
    familyBands &&
    (model_info || model_info === null) &&
    (prompts || prompts === null)
  ) {
    updateChart()
  }

  // Svelte action to initialize chart when element is added to DOM
  function initChart(node: HTMLElement) {
    chartInstance = echarts.init(node)

    const resizeObserver = new ResizeObserver(() => {
      chartInstance?.resize()
      recordChartSize(node)
    })
    resizeObserver.observe(node)

    // Track the pointer at the zrender level: it updates before the tooltip is
    // built, so the formatter knows which axis is under the cursor.
    const zr = chartInstance.getZr()
    const onPointerMove = (event: {
      target?: { __dimIdx?: number }
      offsetX?: number
      offsetY?: number
    }) => {
      hoveredAxisIndex = axisIndexFromPointer(event)
    }
    const onPointerOut = () => {
      hoveredAxisIndex = null
    }
    zr.on("mousemove", onPointerMove)
    zr.on("globalout", onPointerOut)

    // Measured before the first draw so bottom mode never paints the
    // unmeasured percentage fallback and then jumps to the real geometry
    recordChartSize(node)
    updateChart()

    return {
      destroy() {
        resizeObserver.disconnect()
        zr.off("mousemove", onPointerMove)
        zr.off("globalout", onPointerOut)
        chartInstance?.dispose()
        chartInstance = null
      },
    }
  }
</script>

<!-- Radar charts don't really work with <3 items. Counts the usage axes too: they
     are axes like any other, and a task with one or two eval scores still has a
     chart worth drawing once cost, latency and tokens are on it. -->
{#if chartKeys.length + visibleUsageKeys.length >= MIN_RADAR_AXES}
  <!-- No margin of its own: this card is paired with the metrics radar in a
       grid row and has to be exactly as tall as its neighbour, which a bottom
       margin would eat 24px out of. Spacing belongs to whatever places it. -->
  <div
    class="bg-white border border-gray-200 rounded-lg p-6 h-full flex flex-col"
  >
    <div class="flex flex-row gap-4 items-start">
      <div class="flex-grow">
        <div class="text-xl font-bold">{title}</div>
        <div
          class="text-sm text-gray-500 {notShownNote || showFamilyKey
            ? ''
            : 'mb-4'}"
        >
          {subtitle}
        </div>
        {#if notShownNote}
          <div class="text-xs text-gray-400 mt-1 {showFamilyKey ? '' : 'mb-4'}">
            {notShownNote}
          </div>
        {/if}
        {#if showFamilyKey}
          <!-- The ring says which family is which and where each one ends; what
               it cannot say without being counted is HOW MANY criteria each
               covers, so that is all this line is for. No swatch, and no
               colour: the arc tones are a separator, not an identity, and a key
               to them would invite reading them as one. Both this and the arcs
               are built from the same runs, so an axis dropped for having no
               result cannot leave a name here without an arc on the chart. -->
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 mb-4">
            <span class="text-xs text-gray-400"> Score families: </span>
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
        <div class="join">
          <button
            type="button"
            class="join-item btn btn-sm {absoluteScale ? '' : 'btn-active'}"
            aria-pressed={!absoluteScale}
            on:click={() => setScale(false)}
          >
            Relative
          </button>
          <button
            type="button"
            class="join-item btn btn-sm {absoluteScale ? 'btn-active' : ''}"
            aria-pressed={absoluteScale}
            on:click={() => setScale(true)}
          >
            Full Scale
          </button>
        </div>
        <InfoTooltip tooltip_text={scaleTooltip} position="bottom" />
      </div>
    </div>
    {#if hasData}
      <!-- With the legend underneath, the radar is as big as the box is tall,
           so this floor is what makes it the section's centrepiece rather than
           a thumbnail: 640px carries a ~455px polygon plus wrapped axis names
           top and bottom and the legend row. The max width stops a page-wide
           card from stranding the plot in acres of empty margin - a radar is
           square, so width past the point where height binds is dead space. -->
      <div
        use:initChart
        class="w-full flex-1 {legend_position === 'bottom'
          ? 'min-h-[640px] max-w-[1080px] mx-auto'
          : 'min-h-[500px] xl:min-h-[620px]'}"
      ></div>
    {:else}
      <ChartNoData
        title={noResultAxisCount > 0
          ? "Not Enough Shared Scores"
          : "No Data Available"}
        message={noDataMessage}
      />
    {/if}
  </div>
{/if}

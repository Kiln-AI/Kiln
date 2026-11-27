<script lang="ts">
  // The eval check panel, under the review start screen: what the whole
  // judged batch says about the eval, before the owner reviews a sample. It
  // never holds up the review; Start sits above it, and every answer is
  // optional. The free numbers show at once; sorting the failures by cause
  // is one paid call that only the owner's button starts.
  import { onDestroy } from "svelte"
  import SettingsHeader from "$lib/ui/settings_header.svelte"
  import PropertyList from "$lib/ui/property_list.svelte"
  import Warning from "$lib/ui/warning.svelte"
  import type { UiProperty } from "$lib/ui/property_list"
  import type { GroundingDrop } from "./batch_plan_guidance"
  import {
    answers_summary,
    cases_per_fixture,
    clip,
    drops_by_reason,
    failures_without_reasoning,
    fault_counts,
    grouping_offer_text,
    grouping_scope_text,
    headroom,
    headroom_text,
    on_target_sentence,
    OWNER_ANSWERS,
    percent,
    question_rows,
    rehearsal_check,
    rule_label,
    run_config_phrase,
    type DropCount,
    type FailureGroupingState,
    type Headroom,
    type OwnerAnswer,
    type OwnerAnswers,
    type PanelCase,
    type RehearsalCheck,
  } from "./eval_check"

  export let cases: PanelCase[]
  export let drops: GroundingDrop[] = []
  export let spec_text: string
  export let grouping: FailureGroupingState
  export let judged_noun: string = "example"
  // The run config the batch was driven with; the panel names it.
  export let run_config_name: string | null = null
  // Starts the one paid grouping call.
  export let on_group_failures: () => void = () => {}
  // The panel left the screen: a grouping still running is dropped.
  export let on_leave: () => void = () => {}
  // The answers so far, held by the page for the batch, and the callback that
  // gets every answer so far after each pick.
  export let answers: OwnerAnswers = {}
  export let on_answers_change: (answers: OwnerAnswers) => void = () => {}

  $: h = headroom(cases)
  $: failed = h.total - h.passed
  $: no_reasoning = failures_without_reasoning(cases)
  $: rehearsal = rehearsal_check(cases)
  $: groupable = failed - no_reasoning
  $: spread = cases_per_fixture(cases)
  $: dropped = drops_by_reason(drops)
  $: rule = rule_label(spec_text, grouping)
  $: rows = question_rows(h, grouping)

  $: properties = summary_properties(
    h,
    rehearsal,
    dropped,
    judged_noun,
    run_config_name,
  )

  function summary_properties(
    h: Headroom,
    rehearsal: RehearsalCheck | null,
    dropped: DropCount[],
    noun: string,
    run_config: string | null,
  ): UiProperty[] {
    const list: UiProperty[] = [
      {
        name: "Pass Rate",
        value: `${percent(h.passed, h.total)} (${h.passed} of ${h.total} ${noun}s pass)`,
        tooltip: `How many cases ${run_config_phrase(run_config)} passes. Near 100% the eval can't show an improvement; near 0% some cases may be impossible.`,
        warn_icon: h.verdict !== "ok",
      },
    ]
    if (rehearsal) {
      list.push({
        name: "Rehearsal Fails",
        value: `${rehearsal.failed.length} of ${rehearsal.judged}`,
        tooltip:
          "Before each case ran, the environment setup model acted it out as a well-behaved agent would, and the judge graded that run when the cases were set up. Models wrote and graded the rehearsal, and it has one user message, so a fail means look at this case, not that the case is wrong. The case still ran. Counted over the rehearsals the judge graded.",
        warn_icon: rehearsal.failed.length > 0,
      })
    }
    if (dropped.length > 0) {
      list.push({
        name: "Dropped in Grounding",
        value: dropped.map((d) => `${d.count} ${d.label}`).join(", "),
      })
    }
    return list
  }

  onDestroy(() => on_leave())

  function pick(key: string, answer: OwnerAnswer) {
    on_answers_change({ ...answers, [key]: answer })
  }
</script>

<div class="flex flex-col gap-6" data-eval-check-panel>
  <SettingsHeader
    title="Check This Eval"
    subtitle={`What all ${h.total} judged ${judged_noun}s say about the eval. Optional: you can start the review at any time.`}
  />

  <PropertyList {properties} />

  {#if h.verdict !== "ok"}
    <Warning
      warning_color="warning"
      warning_message={headroom_text(h, run_config_name)}
    />
  {/if}

  {#if no_reasoning > 0}
    <Warning
      warning_color="gray"
      warning_icon="info"
      warning_message={`${no_reasoning} of ${failed} failures have no judge reasoning, so they can't be sorted by cause. To get reasoning, choose a higher Judge Thinking Level in Generation Settings and create the eval data again.`}
    />
  {/if}

  {#if rehearsal && rehearsal.failed.length > 0}
    <div class="flex flex-col gap-3">
      <SettingsHeader
        title="Rehearsal Fails"
        subtitle="The judge failed a well-behaved run of these cases. Models wrote and graded the rehearsal, and it has one user message, so a fail means look at this case, not that the case is wrong."
        show_divider={false}
      />
      <div class="rounded-lg border">
        <table class="table" data-rehearsal-fails>
          <thead>
            <tr><th>Case</th><th>Judge Reasoning</th></tr>
          </thead>
          <tbody>
            {#each rehearsal.failed as failure (failure.trace_id)}
              <tr>
                <td>{clip(failure.raw_input, 200)}</td>
                <td class="text-gray-500">
                  {clip(failure.rehearsal_reasoning ?? "", 600)}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  {#if failed === 0}
    <p class="text-sm" data-grouping-status>
      No failures to sort: every {judged_noun} passed.
    </p>
  {:else if groupable === 0}
    <p class="text-sm text-gray-500" data-grouping-status>
      No failure has judge reasoning to sort by cause.
    </p>
  {:else if grouping.status === "idle"}
    <div class="flex flex-col gap-3 items-start" data-grouping-status>
      <p class="text-sm">{grouping_offer_text(failed, groupable)}</p>
      <button class="btn btn-sm" on:click={on_group_failures}>
        Group the Failures
      </button>
    </div>
  {:else if grouping.status === "loading"}
    <p
      class="text-sm text-gray-500 flex items-center gap-2"
      data-grouping-status
    >
      <span class="loading loading-spinner loading-xs"></span>
      Sorting the failures by cause.
    </p>
  {:else if grouping.status === "unavailable"}
    <div class="flex flex-col gap-3 items-start">
      <Warning
        warning_color="gray"
        warning_icon="info"
        warning_message={`Grouping unavailable: ${grouping.message} The numbers above still hold.`}
      />
      <button class="btn btn-sm" on:click={on_group_failures}>
        Try Again
      </button>
    </div>
  {:else if grouping.status === "ready"}
    <div class="flex flex-col gap-3">
      <SettingsHeader
        title="Who Failed"
        subtitle={grouping_scope_text(grouping.grouping, failed)}
        show_divider={false}
      />
      <div class="rounded-lg border">
        <table class="table" data-who-failed>
          <thead>
            <tr><th>Cause</th><th class="text-right">Failures</th></tr>
          </thead>
          <tbody>
            {#each fault_counts(grouping.grouping) as row (row.kind)}
              <tr>
                <td>{row.label}</td>
                <td class="text-right">{row.count}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>

    <div class="flex flex-col gap-3">
      <SettingsHeader title="What Failed" show_divider={false} />
      <div class="rounded-lg border">
        <table class="table" data-what-failed>
          <thead>
            <tr>
              <th>Group</th>
              <th class="text-right">Count</th>
              <th>Example</th>
              <th>About the Rule</th>
            </tr>
          </thead>
          <tbody>
            {#each grouping.grouping.groups as group (group.name)}
              <tr>
                <td>{group.name}</td>
                <td class="text-right">{group.count}</td>
                <td class="text-gray-500">{group.example}</td>
                <td>{group.about_rule ? "Yes" : "No"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="text-sm" data-on-target>
        {on_target_sentence(grouping.grouping)}
      </p>
    </div>
  {/if}

  {#if spread}
    <div class="flex flex-col gap-3">
      <SettingsHeader title="Cases per Starting State" show_divider={false} />
      {#if spread.crowded}
        <Warning
          warning_color="warning"
          warning_message={`One starting state holds ${spread.crowded.count} of ${spread.total} cases: ${spread.crowded.fixture}. A change tuned on it may not carry over.`}
        />
      {/if}
      <div class="rounded-lg border">
        <table class="table" data-fixtures>
          <thead>
            <tr><th>Starting State</th><th class="text-right">Cases</th></tr>
          </thead>
          <tbody>
            {#each spread.rows as row (row.fixture)}
              <tr>
                <td>
                  {row.fixture}
                  {#if row.variants.length > 0}
                    <ul
                      class="text-xs text-gray-500 mt-1"
                      data-fixture-variants
                    >
                      {#each row.variants as variant (variant.label)}
                        <li>{variant.label}: {variant.count}</li>
                      {/each}
                    </ul>
                  {/if}
                </td>
                <td class="text-right">{row.count}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}

  <div class="flex flex-col gap-3">
    <SettingsHeader
      title="Is This What You Meant?"
      subtitle={`This eval is meant to measure: ${rule}.`}
      show_divider={false}
    />
    <div class="rounded-lg border">
      <table class="table" data-owner-question>
        <tbody>
          {#each rows as row (row.key)}
            <tr>
              <td>{row.label}</td>
              <td>
                <div class="flex flex-wrap gap-1 justify-end">
                  {#each OWNER_ANSWERS as answer (answer.value)}
                    <button
                      class="btn btn-sm {answers[row.key] === answer.value
                        ? 'btn-secondary'
                        : 'btn-outline'}"
                      aria-pressed={answers[row.key] === answer.value}
                      on:click={() => pick(row.key, answer.value)}
                      >{answer.label}</button
                    >
                  {/each}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    {#if answers_summary(answers)}
      <p class="text-sm text-gray-500" data-answers-summary>
        {answers_summary(answers)}
      </p>
    {/if}
  </div>
</div>

<script lang="ts">
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { TaskOutputRatingType } from "$lib/types"
  import { rating_name } from "$lib/utils/formatters"

  export let output_score_type: TaskOutputRatingType
</script>

<div class="font-normal">
  {#if output_score_type === "five_star"}
    1 to 5
    <span class="ml-[-5px]">
      <InfoTooltip tooltip_text="1 to 5 stars, where 5 is best" />
    </span>
  {:else if output_score_type === "pass_fail"}
    pass/fail
    <span class="ml-[-5px]">
      <InfoTooltip tooltip_text="0 is fail and 1 is pass" />
    </span>
  {:else if output_score_type === "pass_fail_critical"}
    pass/fail/critical
    <InfoTooltip
      tooltip_text="-1 is critical failure, 0 is fail, and 1 is pass"
      no_pad={true}
    />
  {:else if output_score_type === "custom"}
    number
    <InfoTooltip
      tooltip_text="Any finite number. Custom metrics are unbounded values like token counts, cost, or latency."
      no_pad={true}
    />
  {:else}
    {rating_name(output_score_type)}
  {/if}
</div>

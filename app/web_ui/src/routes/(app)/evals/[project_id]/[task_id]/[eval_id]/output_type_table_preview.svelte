<script lang="ts">
  import InfoTooltip from "$lib/ui/info_tooltip.svelte"
  import type { TaskOutputRatingType } from "$lib/types"
  import { _ } from "svelte-i18n"

  export let output_score_type: TaskOutputRatingType
</script>

<div class="font-normal">
  {#if output_score_type === "five_star"}
    1 to 5
    <span class="ml-[-5px]">
      <InfoTooltip tooltip_text={$_("evaluation.one_to_five_stars")} />
    </span>
  {:else if output_score_type === "pass_fail"}
    pass/fail
    <span class="ml-[-5px]">
      <InfoTooltip tooltip_text={$_("evaluation.pass_fail_desc")} />
    </span>
  {:else if output_score_type === "pass_fail_critical"}
    pass/fail/critical
    <InfoTooltip
      tooltip_text={$_("evaluation.pass_fail_critical_desc")}
      no_pad={true}
    />
  {:else}
    {output_score_type}
  {/if}
</div>

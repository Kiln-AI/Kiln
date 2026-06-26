<script lang="ts">
  import type { V2EvalType } from "$lib/utils/eval_types/registry"

  import ExactMatchIcon from "$lib/ui/icons/eval_types/exact_match_icon.svelte"
  import PatternMatchIcon from "$lib/ui/icons/eval_types/pattern_match_icon.svelte"
  import ContainsIcon from "$lib/ui/icons/eval_types/contains_icon.svelte"
  import SetCheckIcon from "$lib/ui/icons/eval_types/set_check_icon.svelte"
  import ToolCallCheckIcon from "$lib/ui/icons/eval_types/tool_call_check_icon.svelte"
  import StepCountCheckIcon from "$lib/ui/icons/eval_types/step_count_check_icon.svelte"
  import LlmJudgeIcon from "$lib/ui/icons/eval_types/llm_judge_icon.svelte"
  import CodeEvalIcon from "$lib/ui/icons/eval_types/code_eval_icon.svelte"

  export let evalType: V2EvalType

  const iconComponents: Record<V2EvalType, typeof ExactMatchIcon> = {
    exact_match: ExactMatchIcon,
    pattern_match: PatternMatchIcon,
    contains: ContainsIcon,
    set_check: SetCheckIcon,
    tool_call_check: ToolCallCheckIcon,
    step_count_check: StepCountCheckIcon,
    llm_judge: LlmJudgeIcon,
    code_eval: CodeEvalIcon,
  }

  $: iconComponent = iconComponents[evalType]
</script>

<svelte:component this={iconComponent} />

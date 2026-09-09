<script lang="ts">
  import {
    type V2EvalType,
    type V2EvalTypeMetadata,
    evalTypeJudgeLabel,
  } from "$lib/utils/eval_types/registry"
  import EvalTypeTags from "./select/eval_type_tags.svelte"
  import Callout from "$lib/ui/callout.svelte"
  import EvalTypeIcon from "$lib/components/eval_types/eval_type_icon.svelte"

  export let evalType: V2EvalType
  export let metadata: V2EvalTypeMetadata

  $: introTitle = evalTypeJudgeLabel(evalType)
</script>

<div data-testid="eval-type-intro">
  <Callout
    testid="eval-type-intro-card"
    title={introTitle}
    description={metadata.explainer || metadata.description}
    example={metadata.example || null}
  >
    <div
      slot="icon"
      class="flex items-center justify-center w-full h-full"
      aria-hidden="true"
    >
      <EvalTypeIcon {evalType} />
    </div>
    <EvalTypeTags slot="tags" tags={metadata.tags} />
  </Callout>
</div>

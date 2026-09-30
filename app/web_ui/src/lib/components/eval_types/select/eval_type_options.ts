import type { OptionListItem } from "$lib/ui/option_list_types"
import {
  ALL_V2_EVAL_TYPES,
  getV2EvalTypeMetadata,
} from "$lib/utils/eval_types/registry"
import { getEvalTypeIconComponent } from "$lib/components/eval_types/eval_type_icon.svelte"

/**
 * Build the judge-type picker options from the V2 eval type registry, shaped
 * for the reusable OptionList component. The option `id` is the V2EvalType.
 */
export function buildEvalTypeOptions(): OptionListItem[] {
  return ALL_V2_EVAL_TYPES.map((evalType) => {
    const metadata = getV2EvalTypeMetadata(evalType)
    return {
      id: evalType,
      name: metadata.label,
      description: metadata.description,
      icon: getEvalTypeIconComponent(evalType),
      recommended: metadata.recommended ?? false,
      tags: metadata.tags,
    }
  })
}

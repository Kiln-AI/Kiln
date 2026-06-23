<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import Output from "$lib/ui/output.svelte"
  import type { InputTransform } from "$lib/types"
  import { getInputTransformDisplay } from "$lib/utils/run_config_formatters"

  export let transform: InputTransform

  let dialog: Dialog

  export function show() {
    dialog?.show()
  }

  $: display = getInputTransformDisplay(transform)

  function getTemplateBody(t: InputTransform): string {
    switch (t.type) {
      case "jinja":
        return t.template
      default: {
        const _exhaustive: never = t.type
        throw new Error(`Unknown input transform type: ${_exhaustive}`)
      }
    }
  }
</script>

<Dialog
  bind:this={dialog}
  title="Input Transformer"
  subtitle={display.modalSubtitle}
  width="wide"
>
  <Output raw_output={getTemplateBody(transform)} show_border={true} />
</Dialog>

<script lang="ts">
  // The guidance row shared by every synthetic data surface. No form
  // container, submit button or header: each surface wraps the row and owns
  // its own submit. The Guidance label and description are hardcoded so the
  // wording stays identical wherever the row appears.
  import FormElement from "$lib/utils/form_element.svelte"
  import Warning from "$lib/ui/warning.svelte"

  export let guidance: string
  // The guidance field's DOM id. Overridable because two instances can be
  // mounted at once (a page and a dialog), and ids have to stay unique.
  export let guidance_id = "batch_guidance"
  // The text the guidance box started from. When set and the user has edited
  // away from it, a Reset link offers to put it back.
  export let guidance_template: string | null = null
  // Example text shown in the empty guidance box. Surfaces that start the box
  // empty (no template to reset to) use it to show the shape of a good answer.
  export let guidance_placeholder: string | null = null
  // Whether an empty guidance box is a valid submission. Off by default so the
  // surfaces that prefill guidance keep requiring one; surfaces where a blank
  // steer is the intended default turn it on, which also renders the standard
  // "Optional" badge so the empty box reads as deliberate rather than unfilled.
  export let guidance_optional: boolean = false

  // Optional caution rendered after the rows, so in a dialog it sits directly
  // above the submit button the surrounding context owns. It is written flush
  // against the field above it (no gap in the markup) so that leaving it unset
  // renders nothing at all, not a stray whitespace node.
  export let warning_message: string | null = null

  // Slot content lands between the rows and the warning, so a surface that
  // adds a field (the eval builder's Data Guide checkbox) keeps the warning
  // directly above its submit. Written flush like the warning, so with no
  // content nothing renders.

  function reset_guidance() {
    if (guidance_template !== null) {
      guidance = guidance_template
    }
  }
</script>

<FormElement
  id={guidance_id}
  label="Guidance"
  description={`This allows you to control the dataset you are generating. For example, "10% of the dataset should be in Spanish."`}
  inputType="textarea"
  height="medium"
  optional={guidance_optional}
  placeholder={guidance_placeholder}
  bind:value={guidance}
  inline_action={guidance_template && guidance !== guidance_template
    ? {
        handler: reset_guidance,
        label: "Reset",
      }
    : null}
/><slot /><Warning {warning_message} warning_color="warning" />

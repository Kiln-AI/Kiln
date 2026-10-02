<script lang="ts">
  export let schema_string: string | null = null
  export let warn_about_required: boolean = false
  export let structured_label: string = ""

  // The create page treats plaintext mode as "use a static schema", which lets
  // this stub avoid parsing any real JSON schema during the wizard flow.
  export function is_plaintext(): boolean {
    return true
  }
  export function get_schema_string(): string | null {
    return schema_string
  }
</script>

<div
  data-testid="schema-section-stub"
  data-warn={warn_about_required}
  data-label={structured_label}
></div>

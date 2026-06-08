<script lang="ts">
  export let properties: Record<string, unknown> = {
    type: "code_eval",
    code: "def score(): pass",
    timeout_seconds: 30,
  }

  export function getProperties(): Record<string, unknown> {
    return properties
  }
</script>

<div data-testid="v2-form-stub">V2 Form Stub</div>

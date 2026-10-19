<script lang="ts" context="module">
  let _initial_code = "def score(): pass"

  export function setInitialCode(code: string) {
    _initial_code = code
  }

  export function resetInitialCode() {
    _initial_code = "def score(): pass"
  }
</script>

<script lang="ts">
  export let properties: Record<string, unknown> = {
    type: "code_eval",
    code: _initial_code,
    timeout_seconds: 30,
  }

  export let code_string: string = (properties.code as string) ?? ""

  export function getProperties(): Record<string, unknown> {
    return properties
  }
</script>

<div data-testid="v2-form-stub">V2 Form Stub</div>

<script lang="ts">
  export let value: string = ""
  export let min_height: string = ""

  export function setValue(v: string): void {
    value = v
  }
</script>

<div data-testid="code-editor-stub" data-min-height={min_height}>{value}</div>

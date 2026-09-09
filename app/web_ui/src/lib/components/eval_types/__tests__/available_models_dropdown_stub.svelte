<script lang="ts">
  export let task_id: string = ""
  export let model: string | undefined = undefined
  export let model_name: string | undefined = undefined
  export let provider_name: string | undefined = undefined
  export let settings: Record<string, unknown> = {}
</script>

<div data-testid="available-models-dropdown-stub">
  Dropdown Stub (task={task_id}, model={model}, model_name={model_name},
  provider_name={provider_name}, settings={JSON.stringify(settings)})
</div>

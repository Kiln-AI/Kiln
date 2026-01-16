<script lang="ts">
  import EvalIcon from "$lib/ui/icons/eval_icon.svelte"

  export let project_id: string
  export let task_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <div class="h-12 w-12 mr-2">
        <EvalIcon />
      </div>
    </div>
    <div class="font-medium text-lg">
      Kiln Prompt Optimizer automatically optimizes your prompts.
    </div>
    <div>
      Kiln Prompt Optimizer automatically optimizes your prompts to improve
      performance on your evals.
    </div>
    <a
      href={`/gepa/${project_id}/${task_id}/create_gepa`}
      class="btn btn-primary mt-2"
    >
      Run Kiln Prompt Optimization
    </a>
  </div>
</div>

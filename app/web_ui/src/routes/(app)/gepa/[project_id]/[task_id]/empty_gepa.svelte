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
      GEPA Generates Eval Prompts and Augmented Data
    </div>
    <div>
      Use GEPA to automatically optimize your prompts and generate high-quality
      evaluation data for your tasks.
    </div>
    <a
      href={`/gepa/${project_id}/${task_id}/create_gepa`}
      class="btn btn-primary mt-2"
    >
      Create a GEPA Job
    </a>
  </div>
</div>

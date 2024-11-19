<script lang="ts">
  export let project_id: string
  export let task_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="font-medium">Your dataset for this task is empty.</div>
    <div>Adding data will allow the model to improve at it's task.</div>
    <div>To get started, generate some synthetic data or add data manually</div>
  </div>
  <div class="flex flex-row gap-6 justify-center flex-col">
    <a href={`/generate/${project_id}/${task_id}`} class="btn btn-primary">
      Generate Synthetic Data
    </a>
    <a href="/run" class="btn btn-primary"> Manually Add Data </a>
  </div>
</div>

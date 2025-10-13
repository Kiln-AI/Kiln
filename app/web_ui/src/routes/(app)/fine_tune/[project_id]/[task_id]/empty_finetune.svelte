<script lang="ts">
  import FinetuneIcon from "$lib/ui/finetune_icon.svelte"

  export let project_id: string
  export let task_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <div class="h-12 w-12 mr-2">
        <FinetuneIcon />
      </div>
    </div>
    <div class="font-medium text-lg">
      Fine-Tuning Learns from Your Dataset to Create Custom Models
    </div>
    <div>
      Fine-tuned models can be faster, cheaper and more accurate than standard
      models.
    </div>
    <a
      href={`/fine_tune/${project_id}/${task_id}/create_finetune`}
      class="btn btn-primary mt-2"
    >
      Create a Fine-Tune
    </a>
    <a
      href="https://docs.kiln.tech/docs/fine-tuning-guide"
      class="btn"
      target="_blank"
    >
      Fine Tuning Guide
    </a>
  </div>
</div>

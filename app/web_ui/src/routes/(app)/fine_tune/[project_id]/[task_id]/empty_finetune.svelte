<script lang="ts">
  export let project_id: string
  export let task_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-12 h-12 mr-2"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <circle
          cx="12"
          cy="12"
          r="2"
          transform="rotate(180 12 12)"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <circle
          cx="20"
          cy="14"
          r="2"
          transform="rotate(180 20 14)"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <circle
          cx="2"
          cy="2"
          r="2"
          transform="matrix(-1 8.74228e-08 8.74228e-08 1 6 8)"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M12 8L12 5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M20 10L20 5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M4 14L4 19"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M12 19L12 16"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M20 19L20 18"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M4 5L4 6"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
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
      href="https://docs.getkiln.ai/docs/fine-tuning-guide"
      class="btn"
      target="_blank"
    >
      Fine Tuning Guide
    </a>
  </div>
</div>

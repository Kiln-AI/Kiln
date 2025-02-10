<script lang="ts">
  export let project_id: string
  export let task_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524492/database -->
      <svg
        class="w-12 h-12"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M4 18V6"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M20 6V18"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M12 10C16.4183 10 20 8.20914 20 6C20 3.79086 16.4183 2 12 2C7.58172 2 4 3.79086 4 6C4 8.20914 7.58172 10 12 10Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M20 12C20 14.2091 16.4183 16 12 16C7.58172 16 4 14.2091 4 12"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M20 18C20 20.2091 16.4183 22 12 22C7.58172 22 4 20.2091 4 18"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
    </div>
    <div class="font-medium text-lg">Your dataset for this task is empty.</div>
    <div>Adding data will allow the model to improve at it's task.</div>
    <div>To get started, generate some synthetic data or add data manually</div>

    <a href="/run" class="btn btn-primary"> Manually Add Data </a>
    <a href={`/generate/${project_id}/${task_id}`} class="btn">
      Generate Synthetic Data
    </a>
  </div>
</div>

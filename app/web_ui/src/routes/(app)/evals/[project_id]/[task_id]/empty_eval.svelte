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
        <path
          d="M2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2C16.714 2 19.0711 2 20.5355 3.46447C22 4.92893 22 7.28595 22 12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12Z"
          stroke="#1C274C"
          stroke-width="1.5"
        />
        <path
          d="M6 15.8L7.14286 17L10 14"
          stroke="#1C274C"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M6 8.8L7.14286 10L10 7"
          stroke="#1C274C"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M13 9L18 9"
          stroke="#1C274C"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M13 16L18 16"
          stroke="#1C274C"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <div class="font-medium text-lg">
      Improve Quality and Move Faster with Evaluations
    </div>
    <div>Create powerful evaluators using LLMs to judge performance.</div>
    <div>
      Quickly compare many approaches to find what works best for your task.
    </div>
    <div>
      Ensure quality over time, back testing prior bugs and benchmarking new
      approaches.
    </div>
    <a
      href={`/evals/${project_id}/${task_id}/create_evaluator`}
      class="btn btn-primary mt-2"
    >
      Create an Evaluator
    </a>
    <a
      href="https://docs.kiln.tech/docs/evaluations"
      class="btn"
      target="_blank"
    >
      Evals Guide
    </a>
  </div>
</div>

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
      Improve Quality and Move Faster with Evaluations
    </div>
    <div>
      Create powerful evaluators for your task or search tools using LLMs to
      judge performance.
    </div>
    <div>Quickly compare many approaches to find what works best.</div>
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

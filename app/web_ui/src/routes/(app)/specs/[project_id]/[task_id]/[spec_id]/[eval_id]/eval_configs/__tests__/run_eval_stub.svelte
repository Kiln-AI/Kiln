<script lang="ts">
  export let eval_type: string = ""
  export let run_all: boolean = false
  export let btn_primary: boolean = true
  export let btn_size: string = "mid"
  export let project_id: string = ""
  export let task_id: string = ""
  export let eval_id: string = ""
  export let eval_state: string = "not_started"
  export let on_run_complete: () => void = () => {}
</script>

<button
  data-testid="run-eval-stub"
  data-eval-type={eval_type}
  data-run-all={run_all}
  data-btn-primary={btn_primary}
  data-btn-size={btn_size}
  data-ids={`${project_id}/${task_id}/${eval_id}`}
  data-eval-state={eval_state}
  on:click={on_run_complete}>Run {run_all ? "All Evals" : "Eval"}</button
>

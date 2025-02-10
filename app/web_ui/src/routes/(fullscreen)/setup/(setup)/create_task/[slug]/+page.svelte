<script lang="ts">
  import { page } from "$app/stores"
  import EditTask from "../edit_task.svelte"

  $: project_id = $page.params.slug
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Create a Task
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Let's define what this model should do. We call this a "task".
</h3>

<div
  class="flex-none min-h-[50vh] py-8 px-4 h-full flex flex-col py-18 w-full max-w-[600px] mx-auto"
>
  <EditTask redirect_on_created="/" explicit_project_id={project_id} />
</div>

<div class="grow-[1.5]"></div>

<script lang="ts">
  import SelectTasksMenu from "../../../../(app)/select_tasks_menu.svelte"
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  Select a Task
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  Which task do you want to work on?
</h3>

<div
  class="flex-none min-h-[50vh] py-8 px-4 h-full flex flex-col py-18 mx-auto w-full max-w-[800px]"
>
  <SelectTasksMenu
    new_project_url="/setup/create_project"
    new_task_url="/setup/create_task"
  />
</div>

<div class="grow-[1.5]"></div>

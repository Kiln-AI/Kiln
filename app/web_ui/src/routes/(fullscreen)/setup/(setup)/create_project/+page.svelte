<script lang="ts">
  import EditProject from "./edit_project.svelte"
  import { type Project } from "$lib/types"
  import { _ } from "svelte-i18n"

  let project: Project = {
    v: 1,
    name: "",
    description: "",
  }

  function example_project() {
    project.name = $_("project.example_project_name")
    project.description = $_("project.example_project_description")
  }
</script>

<div class="grow"></div>
<div class="flex-none flex flex-row items-center justify-center">
  <img src="/logo.svg" alt="logo" class="size-8 mb-3" />
</div>
<h1 class="text-2xl lg:text-4xl flex-none font-bold text-center">
  {$_("project.create_project")}
</h1>
<h3 class="text-base font-medium text-center mt-3 max-w-[600px] mx-auto">
  {$_("project.create_project_subtitle")}
</h3>
<h3 class="text-sm text-center mt-1 max-w-[600px] mx-auto">
  {$_("project.just_exploring")}
  <button class="link text-primary" on:click={example_project}
    >{$_("project.create_example")}</button
  >
</h3>

<div
  class="flex-none min-h-[50vh] py-8 px-4 h-full flex flex-col py-18 mx-auto w-full max-w-[500px]"
>
  <EditProject redirect_on_created="/setup/create_task" bind:project />
</div>

<div class="grow-[1.5]"></div>

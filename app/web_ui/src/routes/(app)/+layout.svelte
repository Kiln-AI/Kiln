<script lang="ts">
  import "../../app.css"
  import { current_project, current_task } from "$lib/stores"
  import SelectTasksMenu from "./select_tasks_menu.svelte"
  import { page } from "$app/stores"
  import { ui_state } from "$lib/stores"
  import { update_update_store, update_info } from "$lib/utils/update"
  import { onMount } from "svelte"
  import ProgressWidget from "$lib/ui/progress_widget.svelte"

  onMount(async () => {
    update_update_store()
  })

  enum Section {
    Dataset,
    DocumentsMain,
    DocumentsLibrary,
    DocumentsExtractors,
    SettingsMain,
    SettingsProviders,
    SettingsManageProjects,
    SettingsEditProject,
    SettingsEditTask,
    SettingsAppUpdate,
    Prompts,
    Evals,
    Generate,
    Run,
    FineTune,
    None,
  }

  const settingsSections = [
    Section.SettingsMain,
    Section.SettingsProviders,
    Section.SettingsManageProjects,
    Section.SettingsEditProject,
    Section.SettingsEditTask,
    Section.SettingsAppUpdate,
  ]

  const documentSections = [
    Section.DocumentsMain,
    Section.DocumentsLibrary,
    Section.DocumentsExtractors,
  ]

  function path_start(root: string, pathname: string): boolean {
    if (pathname == root) {
      return true
    } else if (pathname.startsWith(root + "/")) {
      return true
    }
    return false
  }

  let section: Section = Section.None
  $: {
    if (path_start("/dataset", $page.url.pathname)) {
      section = Section.Dataset
    } else if (path_start("/settings/providers", $page.url.pathname)) {
      section = Section.SettingsProviders
    } else if (path_start("/settings/manage_projects", $page.url.pathname)) {
      section = Section.SettingsManageProjects
    } else if (path_start("/settings/edit_project", $page.url.pathname)) {
      section = Section.SettingsEditProject
    } else if (path_start("/settings/edit_task", $page.url.pathname)) {
      section = Section.SettingsEditTask
    } else if (path_start("/settings/check_for_update", $page.url.pathname)) {
      section = Section.SettingsAppUpdate
    } else if (path_start("/settings", $page.url.pathname)) {
      section = Section.SettingsMain
    } else if (path_start("/run", $page.url.pathname)) {
      section = Section.Run
    } else if (path_start("/generate", $page.url.pathname)) {
      section = Section.Generate
    } else if (path_start("/fine_tune", $page.url.pathname)) {
      section = Section.FineTune
    } else if (path_start("/prompts", $page.url.pathname)) {
      section = Section.Prompts
    } else if (path_start("/evals", $page.url.pathname)) {
      section = Section.Evals
    } else if (path_start("/docs/library", $page.url.pathname)) {
      section = Section.DocumentsLibrary
    } else if (path_start("/docs/extractors", $page.url.pathname)) {
      section = Section.DocumentsExtractors
    } else if (path_start("/docs", $page.url.pathname)) {
      section = Section.DocumentsMain
    } else {
      section = Section.None
    }
  }

  function close_task_menu() {
    const menu = document.getElementById("task-menu")
    if (menu instanceof HTMLDetailsElement) {
      menu.open = false
    }
  }
</script>

<div class="drawer lg:drawer-open">
  <input id="main-drawer" type="checkbox" class="drawer-toggle" />
  <div class="drawer-content flex flex-col lg:mr-4 min-h-screen">
    <div class="flex-none h-12 lg:h-6">
      <div class="flex flex-row h-full items-center">
        <label for="main-drawer" class="drawer-button lg:hidden">
          <svg
            class="size-6 mx-3"
            viewBox="0 0 20 20"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
          >
            <path
              fill="currentColor"
              fill-rule="evenodd"
              d="M19 4a1 1 0 01-1 1H2a1 1 0 010-2h16a1 1 0 011 1zm0 6a1 1 0 01-1 1H2a1 1 0 110-2h16a1 1 0 011 1zm-1 7a1 1 0 100-2H2a1 1 0 100 2h16z"
            />
          </svg>
        </label>
        <div class="flex-grow"></div>
      </div>
    </div>

    <div
      class="flex-grow rounded-3xl bg-base-100 shadow-md px-4 md:px-12 py-8 mb-4 border"
    >
      <slot />
    </div>
  </div>
  <div class="drawer-side" on:mouseleave={close_task_menu} role="navigation">
    <label for="main-drawer" aria-label="close sidebar" class="drawer-overlay"
    ></label>

    <ul
      class="menu bg-base-200 text-base-content w-72 lg:w-72 p-4 pt-1 lg:pt-4 min-h-full"
    >
      <li class="hover:bg-transparent flex flex-row justify-end">
        <label
          for="main-drawer"
          class="lg:hidden ml-3 text-2xl cursor-pointer ml-4 pt-[5px]"
        >
          &#x2715;
        </label>
      </li>
      <div class="mb-4 ml-4 mt-2">
        <div class="flex flex-row items-center mx-[-5px] p-0">
          <img src="/images/animated_logo.svg" alt="logo" class="w-8 h-8" />
          <div class="text-lg font-bold ml-1">Kiln AI</div>
        </div>
      </div>
      <li class="mb-4">
        <details id="task-menu">
          <summary>
            <div class="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
              <span class="font-bold whitespace-nowrap">Project:</span>
              <span class="truncate">{$current_project?.name}</span>
              <span class="font-bold whitespace-nowrap">Task:</span>
              <span class="truncate">{$current_task?.name}</span>
            </div>
          </summary>
          <SelectTasksMenu />
        </details>
      </li>
      <li class="menu-lg">
        <a href="/" class={section == Section.Run ? "active" : ""}>
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524827/play-circle -->
          <svg
            class="w-6 h-6 mr-2"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M15.4137 10.941C16.1954 11.4026 16.1954 12.5974 15.4137 13.059L10.6935 15.8458C9.93371 16.2944 9 15.7105 9 14.7868L9 9.21316C9 8.28947 9.93371 7.70561 10.6935 8.15419L15.4137 10.941Z"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
          Run</a
        >
      </li>
      <li class="menu-lg">
        <a
          href={`/dataset/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
          class={section == Section.Dataset ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524492/database -->
          <svg
            class="w-6 h-6 mr-2"
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
          Dataset</a
        >
      </li>

      <li class="menu-lg">
        <a
          href={`/generate/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
          class={section == Section.Generate ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="w-6 h-6 mr-2"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M22 10.5V12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2H13.5"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M16.652 3.45506L17.3009 2.80624C18.3759 1.73125 20.1188 1.73125 21.1938 2.80624C22.2687 3.88124 22.2687 5.62415 21.1938 6.69914L20.5449 7.34795M16.652 3.45506C16.652 3.45506 16.7331 4.83379 17.9497 6.05032C19.1662 7.26685 20.5449 7.34795 20.5449 7.34795M16.652 3.45506L10.6872 9.41993C10.2832 9.82394 10.0812 10.0259 9.90743 10.2487C9.70249 10.5114 9.52679 10.7957 9.38344 11.0965C9.26191 11.3515 9.17157 11.6225 8.99089 12.1646L8.41242 13.9M20.5449 7.34795L14.5801 13.3128C14.1761 13.7168 13.9741 13.9188 13.7513 14.0926C13.4886 14.2975 13.2043 14.4732 12.9035 14.6166C12.6485 14.7381 12.3775 14.8284 11.8354 15.0091L10.1 15.5876M10.1 15.5876L8.97709 15.9619C8.71035 16.0508 8.41626 15.9814 8.21744 15.7826C8.01862 15.5837 7.9492 15.2897 8.03811 15.0229L8.41242 13.9M10.1 15.5876L8.41242 13.9"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
          Synthetic Data</a
        >
      </li>

      <li class="menu-lg">
        <a
          href={`/fine_tune/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
          class={section == Section.FineTune ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="w-6 h-6 mr-2"
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

          Fine Tune</a
        >
      </li>

      <li class="menu-lg">
        <a
          href={`/evals/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
          class={section == Section.Evals ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="w-6 h-6 mr-2"
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

          Evals</a
        >
      </li>

      <li class="menu-lg">
        <a
          href={`/prompts/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
          class={section == Section.Prompts ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="w-6 h-6 mr-2"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M11.25 17C11.25 17.4142 11.5858 17.75 12 17.75C12.4142 17.75 12.75 17.4142 12.75 17H11.25ZM15.25 9.75C15.25 10.1642 15.5858 10.5 16 10.5C16.4142 10.5 16.75 10.1642 16.75 9.75H15.25ZM7.25 9.75C7.25 10.1642 7.58579 10.5 8 10.5C8.41421 10.5 8.75 10.1642 8.75 9.75H7.25ZM15.7071 7.32544L16.2646 6.82371V6.82371L15.7071 7.32544ZM9.5 16.25C9.08579 16.25 8.75 16.5858 8.75 17C8.75 17.4142 9.08579 17.75 9.5 17.75V16.25ZM15 17.75C15.4142 17.75 15.75 17.4142 15.75 17C15.75 16.5858 15.4142 16.25 15 16.25V17.75ZM10 7.75H12V6.25H10V7.75ZM12 7.75H14V6.25H12V7.75ZM12.75 17V7H11.25V17H12.75ZM15.25 9.22222V9.75H16.75V9.22222H15.25ZM7.25 9.22222V9.75H8.75V9.22222H7.25ZM14 7.75C14.4949 7.75 14.7824 7.75196 14.9865 7.78245C15.0783 7.79617 15.121 7.8118 15.1376 7.8194C15.148 7.82415 15.1477 7.82503 15.1496 7.82716L16.2646 6.82371C15.96 6.4853 15.579 6.35432 15.2081 6.29891C14.8676 6.24804 14.4479 6.25 14 6.25V7.75ZM16.75 9.22222C16.75 8.71757 16.7513 8.27109 16.708 7.91294C16.6629 7.54061 16.559 7.15082 16.2646 6.82371L15.1496 7.82716C15.1523 7.83015 15.1609 7.83939 15.1731 7.87221C15.1873 7.91048 15.2048 7.97725 15.2188 8.09313C15.2487 8.34011 15.25 8.67931 15.25 9.22222H16.75ZM10 6.25C9.55208 6.25 9.13244 6.24804 8.79192 6.29891C8.42102 6.35432 8.04 6.4853 7.73542 6.82371L8.85036 7.82716C8.85228 7.82503 8.85204 7.82415 8.86242 7.8194C8.87904 7.8118 8.92168 7.79617 9.01354 7.78245C9.21765 7.75196 9.50511 7.75 10 7.75V6.25ZM8.75 9.22222C8.75 8.67931 8.75129 8.34011 8.78118 8.09313C8.7952 7.97725 8.81273 7.91048 8.8269 7.87221C8.83905 7.83939 8.84767 7.83015 8.85036 7.82716L7.73542 6.82371C7.44103 7.15082 7.3371 7.54061 7.29204 7.91294C7.24871 8.27109 7.25 8.71757 7.25 9.22222H8.75ZM9.5 17.75H15V16.25H9.5V17.75Z"
              fill="#1C274C"
            />
            <path
              d="M2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2C16.714 2 19.0711 2 20.5355 3.46447C22 4.92893 22 7.28595 22 12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12Z"
              stroke="#1C274C"
              stroke-width="1.5"
            />
          </svg>
          Prompts</a
        >
      </li>

      <li class="menu-lg">
        <a
          href={`/docs/${$ui_state.current_project_id}`}
          class={section == Section.DocumentsMain ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
          <svg
            class="w-6 h-6 mr-2"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M3 10C3 6.22876 3 4.34315 4.17157 3.17157C5.34315 2 7.22876 2 11 2H13C16.7712 2 18.6569 2 19.8284 3.17157C21 4.34315 21 6.22876 21 10V14C21 17.7712 21 19.6569 19.8284 20.8284C18.6569 22 16.7712 22 13 22H11C7.22876 22 5.34315 22 4.17157 20.8284C3 19.6569 3 17.7712 3 14V10Z"
              stroke="#1C274C"
              stroke-width="1.5"
            />
            <path
              d="M8 12H16"
              stroke="#1C274C"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M8 8H16"
              stroke="#1C274C"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M8 16H13"
              stroke="#1C274C"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
          Documents</a
        >
        {#if documentSections.includes(section)}
          <ul class="py-2 ml-6">
            <li class="menu-nested-sm">
              <a
                class={section == Section.DocumentsLibrary ? "active" : ""}
                href={`/docs/library/${$ui_state.current_project_id}`}
              >
                Library
              </a>
            </li>
            <li class="menu-nested-sm">
              <a
                class={section == Section.DocumentsExtractors ? "active" : ""}
                href={`/docs/extractors/${$ui_state.current_project_id}`}
              >
                Extractors
              </a>
            </li>
          </ul>
        {/if}
      </li>

      <li class="menu-lg">
        <a
          href="/settings"
          class={section == Section.SettingsMain ? "active" : ""}
        >
          <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools. Attribution: https://www.svgrepo.com/svg/524954/settings -->
          <svg
            class="w-6 h-6 mr-2"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="12"
              cy="12"
              r="3"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M13.7654 2.15224C13.3978 2 12.9319 2 12 2C11.0681 2 10.6022 2 10.2346 2.15224C9.74457 2.35523 9.35522 2.74458 9.15223 3.23463C9.05957 3.45834 9.0233 3.7185 9.00911 4.09799C8.98826 4.65568 8.70226 5.17189 8.21894 5.45093C7.73564 5.72996 7.14559 5.71954 6.65219 5.45876C6.31645 5.2813 6.07301 5.18262 5.83294 5.15102C5.30704 5.08178 4.77518 5.22429 4.35436 5.5472C4.03874 5.78938 3.80577 6.1929 3.33983 6.99993C2.87389 7.80697 2.64092 8.21048 2.58899 8.60491C2.51976 9.1308 2.66227 9.66266 2.98518 10.0835C3.13256 10.2756 3.3397 10.437 3.66119 10.639C4.1338 10.936 4.43789 11.4419 4.43786 12C4.43783 12.5581 4.13375 13.0639 3.66118 13.3608C3.33965 13.5629 3.13248 13.7244 2.98508 13.9165C2.66217 14.3373 2.51966 14.8691 2.5889 15.395C2.64082 15.7894 2.87379 16.193 3.33973 17C3.80568 17.807 4.03865 18.2106 4.35426 18.4527C4.77508 18.7756 5.30694 18.9181 5.83284 18.8489C6.07289 18.8173 6.31632 18.7186 6.65204 18.5412C7.14547 18.2804 7.73556 18.27 8.2189 18.549C8.70224 18.8281 8.98826 19.3443 9.00911 19.9021C9.02331 20.2815 9.05957 20.5417 9.15223 20.7654C9.35522 21.2554 9.74457 21.6448 10.2346 21.8478C10.6022 22 11.0681 22 12 22C12.9319 22 13.3978 22 13.7654 21.8478C14.2554 21.6448 14.6448 21.2554 14.8477 20.7654C14.9404 20.5417 14.9767 20.2815 14.9909 19.902C15.0117 19.3443 15.2977 18.8281 15.781 18.549C16.2643 18.2699 16.8544 18.2804 17.3479 18.5412C17.6836 18.7186 17.927 18.8172 18.167 18.8488C18.6929 18.9181 19.2248 18.7756 19.6456 18.4527C19.9612 18.2105 20.1942 17.807 20.6601 16.9999C21.1261 16.1929 21.3591 15.7894 21.411 15.395C21.4802 14.8691 21.3377 14.3372 21.0148 13.9164C20.8674 13.7243 20.6602 13.5628 20.3387 13.3608C19.8662 13.0639 19.5621 12.558 19.5621 11.9999C19.5621 11.4418 19.8662 10.9361 20.3387 10.6392C20.6603 10.4371 20.8675 10.2757 21.0149 10.0835C21.3378 9.66273 21.4803 9.13087 21.4111 8.60497C21.3592 8.21055 21.1262 7.80703 20.6602 7C20.1943 6.19297 19.9613 5.78945 19.6457 5.54727C19.2249 5.22436 18.693 5.08185 18.1671 5.15109C17.9271 5.18269 17.6837 5.28136 17.3479 5.4588C16.8545 5.71959 16.2644 5.73002 15.7811 5.45096C15.2977 5.17191 15.0117 4.65566 14.9909 4.09794C14.9767 3.71848 14.9404 3.45833 14.8477 3.23463C14.6448 2.74458 14.2554 2.35523 13.7654 2.15224Z"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>

          Settings</a
        >
        {#if settingsSections.includes(section)}
          <ul class="py-2 ml-6">
            <li class="menu-nested-sm {$current_task?.id ? '' : 'hidden'}">
              <a
                class={section == Section.SettingsEditTask ? "active" : ""}
                href={`/settings/edit_task/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
              >
                Edit Task
              </a>
            </li>
            <li class="menu-nested-sm">
              <a
                class={section == Section.SettingsProviders ? "active" : ""}
                href="/settings/providers"
              >
                AI Providers &amp; Models
              </a>
            </li>
            <li class="menu-nested-sm">
              <a
                class={section == Section.SettingsManageProjects
                  ? "active"
                  : ""}
                href="/settings/manage_projects"
              >
                Manage Projects
              </a>
            </li>
            <li class="menu-nested-sm {$current_project?.id ? '' : 'hidden'}">
              <a
                class={section == Section.SettingsEditProject ? "active" : ""}
                href="/settings/edit_project/{$current_project?.id}"
              >
                Edit Project
              </a>
            </li>
            <li class="menu-nested-sm">
              <a
                class={section == Section.SettingsAppUpdate ? "active" : ""}
                href="/settings/check_for_update"
              >
                App Update
              </a>
            </li>
          </ul>
        {/if}
      </li>
      {#if $update_info.update_result && $update_info.update_result.has_update}
        <li class="menu-md mt-4">
          <a href="/settings/check_for_update" class="px-6">
            <span class="bg-primary rounded-full w-2 h-2 mr-1"></span>App Update
            Available</a
          >
        </li>
      {/if}
      <li class="mt-auto pt-2 bg-transparent">
        <ProgressWidget />
      </li>
    </ul>
  </div>
</div>

<style>
  /* Add this style block at the end of your component */
  :global(ul > li.menu-nested-sm) {
    padding: 0.1rem 0.25rem;
  }
  :global(ul > li.menu-nested-sm > a) {
    padding: 0.2rem 1rem;
    font-size: 0.875rem; /* Equivalent to text-sm in Tailwind */
  }
</style>

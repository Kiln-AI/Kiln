<script lang="ts">
  import { Section } from "$lib/ui/section"
  import { ui_state } from "$lib/stores"
  import SidebarRailItem from "./sidebar_rail_item.svelte"
  import FileIcon from "$lib/ui/icons/file_icon.svelte"
  import FinetuneIcon from "$lib/ui/icons/finetune_icon.svelte"
  import SkillsIcon from "$lib/ui/icons/skills_icon.svelte"
  import ToolsIcon from "$lib/ui/icons/tools_icon.svelte"
  import SidebarRailTooltip from "./sidebar_rail_tooltip.svelte"

  export let section: Section

  let hovered = false
  let focused = false
  $: show_tooltip = hovered || focused
</script>

<div class="px-2 my-1 xl:my-2">
  <div class="h-px bg-base-300"></div>
</div>

<div class="flex">
  <a
    href={`/optimize/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
    class="relative flex-1 h-5 flex items-center justify-center text-[9px] font-semibold tracking-wider text-gray-500 hover:bg-base-300/50"
    aria-label="Optimize"
    on:mouseenter={() => (hovered = true)}
    on:mouseleave={() => (hovered = false)}
    on:focus={() => (focused = true)}
    on:blur={() => (focused = false)}
  >
    OPTIMIZE
    <SidebarRailTooltip show={show_tooltip}>Optimize</SidebarRailTooltip>
  </a>
</div>

<SidebarRailItem
  href={`/prompts/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
  active={section === Section.Prompts}
  label="Prompts"
>
  <svg
    slot="icon"
    class="w-full h-full"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      d="M11.25 17C11.25 17.4142 11.5858 17.75 12 17.75C12.4142 17.75 12.75 17.4142 12.75 17H11.25ZM15.25 9.75C15.25 10.1642 15.5858 10.5 16 10.5C16.4142 10.5 16.75 10.1642 16.75 9.75H15.25ZM7.25 9.75C7.25 10.1642 7.58579 10.5 8 10.5C8.41421 10.5 8.75 10.1642 8.75 9.75H7.25ZM15.7071 7.32544L16.2646 6.82371V6.82371L15.7071 7.32544ZM9.5 16.25C9.08579 16.25 8.75 16.5858 8.75 17C8.75 17.4142 9.08579 17.75 9.5 17.75V16.25ZM15 17.75C15.4142 17.75 15.75 17.4142 15.75 17C15.75 16.5858 15.4142 16.25 15 16.25V17.75ZM10 7.75H12V6.25H10V7.75ZM12 7.75H14V6.25H12V7.75ZM12.75 17V7H11.25V17H12.75ZM15.25 9.22222V9.75H16.75V9.22222H15.25ZM7.25 9.22222V9.75H8.75V9.22222H7.25ZM14 7.75C14.4949 7.75 14.7824 7.75196 14.9865 7.78245C15.0783 7.79617 15.121 7.8118 15.1376 7.8194C15.148 7.82415 15.1477 7.82503 15.1496 7.82716L16.2646 6.82371C15.96 6.4853 15.579 6.35432 15.2081 6.29891C14.8676 6.24804 14.4479 6.25 14 6.25V7.75ZM16.75 9.22222C16.75 8.71757 16.7513 8.27109 16.708 7.91294C16.6629 7.54061 16.559 7.15082 16.2646 6.82371L15.1496 7.82716C15.1523 7.83015 15.1609 7.83939 15.1731 7.87221C15.1873 7.91048 15.2048 7.97725 15.2188 8.09313C15.2487 8.34011 15.25 8.67931 15.25 9.22222H16.75ZM10 6.25C9.55208 6.25 9.13244 6.24804 8.79192 6.29891C8.42102 6.35432 8.04 6.4853 7.73542 6.82371L8.85036 7.82716C8.85228 7.82503 8.85204 7.82415 8.86242 7.8194C8.87904 7.8118 8.92168 7.79617 9.01354 7.78245C9.21765 7.75196 9.50511 7.75 10 7.75V6.25ZM8.75 9.22222C8.75 8.67931 8.75129 8.34011 8.78118 8.09313C8.7952 7.97725 8.81273 7.91048 8.8269 7.87221C8.83905 7.83939 8.84767 7.83015 8.85036 7.82716L7.73542 6.82371C7.44103 7.15082 7.3371 7.54061 7.29204 7.91294C7.24871 8.27109 7.25 8.71757 7.25 9.22222H8.75ZM9.5 17.75H15V16.25H9.5V17.75Z"
      fill="currentColor"
    />
    <path
      d="M2 12C2 7.28595 2 4.92893 3.46447 3.46447C4.92893 2 7.28595 2 12 2C16.714 2 19.0711 2 20.5355 3.46447C22 4.92893 22 7.28595 22 12C22 16.714 22 19.0711 20.5355 20.5355C19.0711 22 16.714 22 12 22C7.28595 22 4.92893 22 3.46447 20.5355C2 19.0711 2 16.714 2 12Z"
      stroke="currentColor"
      stroke-width="1.5"
    />
  </svg>
</SidebarRailItem>

<SidebarRailItem
  href="/models"
  active={section === Section.Models}
  label="Models"
>
  <svg
    slot="icon"
    class="w-full h-full"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <path
      d="M19.5617 7C19.7904 5.69523 18.7863 4.5 17.4617 4.5H6.53788C5.21323 4.5 4.20922 5.69523 4.43784 7"
      stroke="currentColor"
      stroke-width="1.5"
    />
    <path
      d="M17.4999 4.5C17.5283 4.24092 17.5425 4.11135 17.5427 4.00435C17.545 2.98072 16.7739 2.12064 15.7561 2.01142C15.6497 2 15.5194 2 15.2588 2H8.74099C8.48035 2 8.35002 2 8.24362 2.01142C7.22584 2.12064 6.45481 2.98072 6.45704 4.00434C6.45727 4.11135 6.47146 4.2409 6.49983 4.5"
      stroke="currentColor"
      stroke-width="1.5"
    />
    <path
      d="M15 18H9"
      stroke="currentColor"
      stroke-width="1.5"
      stroke-linecap="round"
    />
    <path
      d="M2.38351 13.793C1.93748 10.6294 1.71447 9.04765 2.66232 8.02383C3.61017 7 5.29758 7 8.67239 7H15.3276C18.7024 7 20.3898 7 21.3377 8.02383C22.2855 9.04765 22.0625 10.6294 21.6165 13.793L21.1935 16.793C20.8437 19.2739 20.6689 20.5143 19.7717 21.2572C18.8745 22 17.5512 22 14.9046 22H9.09536C6.44881 22 5.12553 22 4.22834 21.2572C3.33115 20.5143 3.15626 19.2739 2.80648 16.793L2.38351 13.793Z"
      stroke="currentColor"
      stroke-width="1.5"
    />
  </svg>
</SidebarRailItem>

<SidebarRailItem
  href={`/tools/${$ui_state.current_project_id}`}
  active={section === Section.Tools}
  label="Tools"
>
  <div slot="icon" class="w-full h-full">
    <ToolsIcon />
  </div>
</SidebarRailItem>

<SidebarRailItem
  href={`/skills/${$ui_state.current_project_id}`}
  active={section === Section.Skills}
  label="Skills"
>
  <div slot="icon" class="w-full h-full">
    <SkillsIcon />
  </div>
</SidebarRailItem>

<SidebarRailItem
  href={`/docs/${$ui_state.current_project_id}`}
  active={section === Section.Documents}
  label="Docs & Search"
>
  <div slot="icon" class="w-full h-full">
    <FileIcon kind="document" />
  </div>
</SidebarRailItem>

<SidebarRailItem
  href={`/fine_tune/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
  active={section === Section.FineTune}
  label="Fine Tune"
>
  <div slot="icon" class="w-full h-full">
    <FinetuneIcon />
  </div>
</SidebarRailItem>

<SidebarRailItem
  href={`/generate/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
  active={section === Section.Generate}
  label="Synthetic Data"
>
  <svg
    slot="icon"
    class="w-full h-full"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
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
</SidebarRailItem>

<div class="px-2 my-1 xl:my-2">
  <div class="h-px bg-base-300"></div>
</div>

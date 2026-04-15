<script lang="ts">
  import { Section } from "$lib/ui/section"
  import { ui_state } from "$lib/stores"
  import SidebarRailItem from "./sidebar_rail_item.svelte"
  import SidebarRailTaskChip from "./sidebar_rail_task_chip.svelte"
  import SidebarRailOptimizeGroup from "./sidebar_rail_optimize_group.svelte"
  import SidebarRailProgress from "./sidebar_rail_progress.svelte"
  import SidebarRailSettings from "./sidebar_rail_settings.svelte"
  import ChatIcon from "$lib/ui/icons/chat_icon.svelte"
  import EvalIcon from "$lib/ui/icons/eval_icon.svelte"

  export let section: Section = Section.None
  export let openTaskDialog: () => void
  export let hasUpdate: boolean = false
</script>

<nav
  class="bg-base-200 text-base-content w-[56px] min-h-full flex flex-col items-stretch pt-3 pb-3 gap-1"
  aria-label="Primary"
>
  <div class="flex justify-center mb-2">
    <img
      src="/images/animated_logo.svg"
      alt="Kiln"
      class="w-7 h-7"
      aria-hidden="true"
    />
  </div>

  <SidebarRailTaskChip on:open={openTaskDialog} />

  <SidebarRailItem href="/" active={section === Section.Run} label="Run">
    <svg
      slot="icon"
      class="w-full h-full"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="1.5" />
      <path
        d="M15.4137 10.941C16.1954 11.4026 16.1954 12.5974 15.4137 13.059L10.6935 15.8458C9.93371 16.2944 9 15.7105 9 14.7868L9 9.21316C9 8.28947 9.93371 7.70561 10.6935 8.15419L15.4137 10.941Z"
        stroke="currentColor"
        stroke-width="1.5"
      />
    </svg>
  </SidebarRailItem>

  <SidebarRailItem href="/chat" active={section === Section.Chat} label="Chat">
    <div slot="icon" class="w-full h-full">
      <ChatIcon />
    </div>
  </SidebarRailItem>

  <SidebarRailItem
    href={`/dataset/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
    active={section === Section.Dataset}
    label="Dataset"
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
  </SidebarRailItem>

  <SidebarRailItem
    href={`/specs/${$ui_state.current_project_id}/${$ui_state.current_task_id}`}
    active={section === Section.Specs}
    label="Specs & Evals"
  >
    <div slot="icon" class="w-full h-full">
      <EvalIcon />
    </div>
  </SidebarRailItem>

  <SidebarRailOptimizeGroup {section} />

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

  <div class="flex-1"></div>

  <SidebarRailProgress />

  <SidebarRailSettings active={section === Section.Settings} {hasUpdate} />
</nav>

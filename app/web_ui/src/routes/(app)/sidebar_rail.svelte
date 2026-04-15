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
</script>

<nav
  class="bg-base-200 text-base-content w-[56px] min-h-full flex flex-col items-stretch pt-1 pb-1 gap-px xl:pt-3 xl:pb-3 xl:gap-1"
  aria-label="Primary"
>
  <div class="flex justify-center mb-3 xl:mb-2">
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

  <div class="flex-1"></div>

  <SidebarRailProgress />

  <SidebarRailSettings active={section === Section.Settings} />
</nav>

<script lang="ts">
  import Intro from "../intro.svelte"
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh]">
  <Intro
    title="Kiln Copilot Required"
    description_markdown="Automatically optimize your prompts with state-of-the-art techniques.\n**Prompt optimization requires a Kiln Copilot paid plan.**"
    action_buttons={[
      {
        label: "Connect Kiln Copilot",
        href: "/prompt_optimization/copilot_auth",
        is_primary: true,
      },
      {
        label: "Learn More",
        href: "https://docs.kiln.tech/docs/prompts/automatic-prompt-optimizer",
        is_primary: false,
        new_tab: true,
      },
    ]}
  >
    <div slot="icon">
      <div class="h-12 w-12">
        <img src="/images/animated_logo.svg" alt="Kiln Copilot" />
      </div>
    </div>
  </Intro>
</div>

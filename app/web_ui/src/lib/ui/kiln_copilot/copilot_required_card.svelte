<script lang="ts">
  import Intro from "../intro.svelte"
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh]">
  <Intro
    title="Kiln Copilot Required"
    description_paragraphs={[
      "Prompt Optimization requires Kiln Copilot to automatically optimize your prompts using state-of-the-art techniques.",
    ]}
    action_buttons={[
      {
        label: "Connect Kiln Copilot",
        href: "/gepa/copilot_auth",
        is_primary: true,
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

<script lang="ts">
  import Intro from "../intro.svelte"

  export let feature_name: string = "This feature"
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh]">
  <Intro
    title="{feature_name} Requires Upgrade"
    description_paragraphs={[
      `${feature_name} is available with an enterprise plan. Contact our sales team to learn more about upgrading your account.`,
    ]}
    action_buttons={[
      {
        label: "Contact Sales",
        href: "mailto:support@kiln.tech",
        is_primary: true,
      },
    ]}
  >
    <div slot="icon">
      <div class="h-12 w-12">
        <img src="/images/animated_logo.svg" alt="Kiln" />
      </div>
    </div>
  </Intro>
</div>

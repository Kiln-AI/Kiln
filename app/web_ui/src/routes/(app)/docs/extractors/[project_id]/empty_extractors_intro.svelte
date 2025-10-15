<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <Intro
    title="Add Extractors to Your Project"
    description_paragraphs={[]}
    action_buttons={[
      {
        label: "Create Extractor",
        href: `/docs/extractors/${project_id}/create_extractor`,
        is_primary: true,
      },
    ]}
  >
    <div slot="description">
      Extractors convert files like PDFs or images into text your models can
      use.
    </div>
    <div slot="icon">
      <img src="/images/scanner.svg" alt="Scanner" class="w-10 h-10" />
    </div>
  </Intro>
</div>

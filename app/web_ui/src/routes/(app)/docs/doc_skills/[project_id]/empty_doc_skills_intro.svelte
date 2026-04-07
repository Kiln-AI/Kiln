<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <Intro
    title="Create a Doc Skill"
    description_paragraphs={[]}
    action_buttons={[
      {
        label: "Create Doc Skill",
        href: `/docs/doc_skills/${project_id}/add_doc_skill`,
        is_primary: true,
      },
    ]}
  >
    <div slot="description">
      Doc Skills turn your uploaded documents into skills that agents can browse
      and read. Upload documents in the Document Library, then create a Doc
      Skill to make them accessible to your agents.
    </div>
    <div slot="icon">
      <img src="/images/doc_skill.svg" alt="Doc Skill" class="w-10 h-10" />
    </div>
  </Intro>
</div>

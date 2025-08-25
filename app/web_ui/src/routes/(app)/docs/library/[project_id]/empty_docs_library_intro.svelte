<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let action: () => void
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <Intro
    title="Add Documents to Your Project"
    description_paragraphs={[]}
    action_buttons={[
      {
        label: "Add Document",
        onClick: action,
        is_primary: true,
      },
    ]}
  >
    <div slot="description">
      Documents can be used for generating synthetic data (question-answer
      pairs), or for RAG (retrieval-augmented generation) in your tasks.
    </div>
    <div slot="icon">
      <img src="/images/doc_library.svg" alt="Library" class="w-10 h-10" />
    </div>
  </Intro>
</div>

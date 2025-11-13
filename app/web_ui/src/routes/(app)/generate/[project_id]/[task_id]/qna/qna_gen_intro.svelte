<script lang="ts">
  import QnaIcon from "$lib/ui/icons/qna_icon.svelte"
  import Intro from "$lib/ui/intro.svelte"

  export let on_select_documents: () => void
</script>

<div class="flex flex-col items-center justify-center min-h-[50vh] mt-12">
  <Intro
    title="Generate Q&A Data"
    description_paragraphs={[]}
    action_buttons={[
      {
        label: "Select Documents",
        onClick: on_select_documents,
        is_primary: true,
      },
    ]}
  >
    <div slot="description">
      Build an eval dataset containing queries and correct answers from your
      document library. <a
        href="https://docs.kiln.tech/docs/evaluations/evaluate-rag-accuracy-q-and-a-evals"
        target="_blank"
        rel="noopener noreferrer"
        class="link">Guide</a
      >.
    </div>
    <div slot="icon" class="h-12 w-12">
      <QnaIcon />
    </div>
  </Intro>
</div>

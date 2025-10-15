<script lang="ts">
  import Intro from "$lib/ui/intro.svelte"

  export let on_select_documents: () => void
</script>

<div class="flex flex-col items-center justify-center min-h-[50vh] mt-12">
  <Intro
    title="Q&A from Documents"
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
      Select documents from your library to generate Q&A pairs. Questions and
      answers will be extracted from the document content to create training
      data. <a
        href="https://docs.kiln.tech/docs/qna-data-generation"
        target="_blank"
        class="link">Guide</a
      >.
    </div>
    <div slot="icon">
      <svg
        class="w-12 h-12"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M7 18C5.17107 18.4117 4 19.0443 4 19.7537C4 20.9943 7.58172 22 12 22C16.4183 22 20 20.9943 20 19.7537C20 19.0443 18.8289 18.4117 17 18"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          d="M14.5 9C14.5 10.3807 13.3807 11.5 12 11.5C10.6193 11.5 9.5 10.3807 9.5 9C9.5 7.61929 10.6193 6.5 12 6.5C13.3807 6.5 14.5 7.61929 14.5 9Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
        <path
          d="M13.2574 17.4936C12.9201 17.8184 12.4693 18 12.0002 18C11.531 18 11.0802 17.8184 10.7429 17.4936C7.6543 14.5008 3.51519 11.1575 5.53371 6.30373C6.6251 3.67932 9.24494 2 12.0002 2C14.7554 2 17.3752 3.67933 18.4666 6.30373C20.4826 11.1514 16.3536 14.5111 13.2574 17.4936Z"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
    </div>
  </Intro>
</div>

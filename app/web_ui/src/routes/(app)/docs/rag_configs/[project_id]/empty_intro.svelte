<script lang="ts">
  export let project_id: string
</script>

<div class="flex flex-col md:flex-row gap-32 justify-center items-center">
  <div class="max-w-[300px] font-light text-sm flex flex-col gap-4">
    <div class="flex justify-center items-center">
      <!-- Uploaded to: SVG Repo, www.svgrepo.com, Generator: SVG Repo Mixer Tools -->
      <svg
        class="w-12 h-12"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        ><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g
          id="SVGRepo_tracerCarrier"
          stroke-linecap="round"
          stroke-linejoin="round"
        ></g><g id="SVGRepo_iconCarrier">
          <path
            d="M20 19L20.5303 19.5303C20.8232 19.2374 20.8232 18.7626 20.5303 18.4697L20 19ZM8 4.25C7.58579 4.25 7.25 4.58579 7.25 5C7.25 5.41421 7.58579 5.75 8 5.75V4.25ZM18.5303 16.4697C18.2374 16.1768 17.7626 16.1768 17.4697 16.4697C17.1768 16.7626 17.1768 17.2374 17.4697 17.5303L18.5303 16.4697ZM17.4697 20.4697C17.1768 20.7626 17.1768 21.2374 17.4697 21.5303C17.7626 21.8232 18.2374 21.8232 18.5303 21.5303L17.4697 20.4697ZM20 18.25H7.5V19.75H20V18.25ZM7.5 12.75H16.5V11.25H7.5V12.75ZM16.5 4.25H8V5.75H16.5V4.25ZM20.5303 18.4697L18.5303 16.4697L17.4697 17.5303L19.4697 19.5303L20.5303 18.4697ZM19.4697 18.4697L17.4697 20.4697L18.5303 21.5303L20.5303 19.5303L19.4697 18.4697ZM20.75 8.5C20.75 6.15279 18.8472 4.25 16.5 4.25V5.75C18.0188 5.75 19.25 6.98122 19.25 8.5H20.75ZM16.5 12.75C18.8472 12.75 20.75 10.8472 20.75 8.5H19.25C19.25 10.0188 18.0188 11.25 16.5 11.25V12.75ZM4.75 15.5C4.75 13.9812 5.98122 12.75 7.5 12.75V11.25C5.15279 11.25 3.25 13.1528 3.25 15.5H4.75ZM7.5 18.25C5.98122 18.25 4.75 17.0188 4.75 15.5H3.25C3.25 17.8472 5.15279 19.75 7.5 19.75V18.25Z"
            fill="currentColor"
          ></path>
          <circle cx="6" cy="5" r="2" stroke="currentColor" stroke-width="1.5"
          ></circle>
        </g></svg
      >
    </div>
    <div class="font-medium text-lg">
      Add RAG Configurations to Your Project
    </div>
    <div>
      Configure your RAG configuration to use your documents in your Kiln Tasks.
    </div>
    <div>
      Combine extractors, chunkers, embeddings and retrievers to create a RAG
      configuration.
    </div>

    <a
      class="btn btn-primary"
      href={`/docs/rag_configs/${project_id}/create_rag_config`}
      >Create RAG Configuration</a
    >
  </div>
</div>

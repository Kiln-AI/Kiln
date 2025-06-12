<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import { extractorProgress } from "$lib/stores/extractor_progress"

  export let btn_size: "normal" | "mid" = "mid"
  export let project_id: string
  export let extractor_config_id: string
  export let disabled: boolean = false

  let run_confirm_dialog: Dialog | null = null
</script>

<button
  {disabled}
  class="btn {btn_size === 'mid'
    ? 'btn-mid'
    : ''} btn-primary whitespace-nowrap"
  on:click={() => {
    run_confirm_dialog?.show()
  }}
>
  <!-- Attribution: https://www.svgrepo.com/svg/526106/play -->
  <svg
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="w-4 h-4"
    ><g id="SVGRepo_bgCarrier" stroke-width="0"></g><g
      id="SVGRepo_tracerCarrier"
      stroke-linecap="round"
      stroke-linejoin="round"
    ></g><g id="SVGRepo_iconCarrier">
      <path
        d="M21.4086 9.35258C23.5305 10.5065 23.5305 13.4935 21.4086 14.6474L8.59662 21.6145C6.53435 22.736 4 21.2763 4 18.9671L4 5.0329C4 2.72368 6.53435 1.26402 8.59661 2.38548L21.4086 9.35258Z"
        fill="currentColor"
      ></path>
    </g></svg
  >
  Run
</button>

<Dialog
  bind:this={run_confirm_dialog}
  title="Extract all documents?"
  action_buttons={[
    { label: "Cancel", isCancel: true },
    {
      label: "Yes, start extraction",
      action: () => {
        extractorProgress.run_extractor(project_id, extractor_config_id)
        run_confirm_dialog?.close()
        return false
      },
      isPrimary: true,
    },
  ]}
>
  <div class="flex flex-col gap-2 font-light mt-4">
    <div>
      This may take a while, depending on the number of documents. We won't
      extract documents that have already been extracted.
    </div>
    <div>If you close this page, you will need to re-run the extractor.</div>
  </div>
</Dialog>

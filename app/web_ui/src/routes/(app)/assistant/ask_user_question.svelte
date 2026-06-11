<script lang="ts">
  import type {
    SuggestedAnswer,
    AskUserQuestionResolution,
  } from "$lib/chat/streaming_chat"

  export let question: string
  export let suggestedAnswers: SuggestedAnswer[] = []
  /** Set once answered → the card collapses to a non-interactive summary. */
  export let resolution: AskUserQuestionResolution | undefined = undefined
  /**
   * Disables the interactive controls while an answer is being sent (or when the
   * input is otherwise gated). The card still renders so the user keeps context.
   */
  export let disabled = false
  export let onPick: (answer: string) => void
  export let onChat: () => void
</script>

{#if resolution}
  <!-- Resolved (ui_design §3): a compact, non-interactive summary of the choice.
       State is conveyed by text + layout (not color alone) for accessibility. -->
  <div
    class="rounded-lg border border-base-content/10 bg-base-content/[0.03] px-3 py-2.5 text-sm"
  >
    <div class="text-xs font-medium text-base-content/50">Your answer</div>
    <div class="mt-0.5 text-base-content/80">
      {#if resolution.kind === "chat"}
        You chose to chat about this.
      {:else}
        You chose: <span class="font-medium">{resolution.answer}</span>
      {/if}
    </div>
  </div>
{:else}
  <div
    class="rounded-lg border border-base-content/10 bg-base-content/[0.03] p-3 flex flex-col gap-3"
    role="group"
    aria-label="Question with suggested answers"
  >
    {#if question}
      <p class="text-sm font-medium text-base-content/90 leading-relaxed">
        {question}
      </p>
    {/if}

    {#if suggestedAnswers.length > 0}
      <div class="flex flex-col gap-2">
        {#each suggestedAnswers as suggestion, i (i)}
          <button
            type="button"
            class="group w-full text-left rounded-md border border-base-content/15 bg-base-100 px-3 py-2 transition-colors hover:border-primary/50 hover:bg-primary/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-50"
            {disabled}
            on:click={() => onPick(suggestion.answer)}
            aria-label={`Send answer: ${suggestion.answer}`}
          >
            <div class="text-sm text-base-content/90">{suggestion.answer}</div>
            {#if suggestion.explanation}
              <div class="mt-0.5 text-xs text-base-content/70 leading-snug">
                {suggestion.explanation}
              </div>
            {/if}
          </button>
        {/each}
      </div>
    {/if}

    <!-- "Chat about this" is ALWAYS present and visually distinct from the
         suggested answers (a ghost button below a thin divider, ui_design §1). -->
    <div class="border-t border-base-content/10 pt-2.5 flex flex-col gap-1">
      <button
        type="button"
        class="btn btn-ghost btn-sm w-full justify-start font-normal text-base-content/80 hover:text-base-content disabled:cursor-not-allowed disabled:opacity-50"
        {disabled}
        on:click={onChat}
        aria-label="Chat about this instead of picking an answer"
      >
        <span aria-hidden="true">▸</span>
        Chat about this
      </button>
      <p class="px-3 text-xs text-base-content/50">
        Refine this by chatting instead.
      </p>
    </div>
  </div>
{/if}

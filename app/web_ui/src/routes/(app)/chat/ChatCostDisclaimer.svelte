<script lang="ts">
  import { fly } from "svelte/transition"
  import { browser } from "$app/environment"
  import { chat_cost_disclaimer_acknowledged } from "$lib/stores"

  function acknowledge(): void {
    chat_cost_disclaimer_acknowledged.set(true)
  }

  $: visible = browser && !$chat_cost_disclaimer_acknowledged
</script>

{#if visible}
  <div
    in:fly={{ y: 6, duration: 220 }}
    class="shrink-0 rounded-2xl border border-warning/30 bg-warning/5 px-4 py-4 sm:px-5 sm:py-5 shadow-sm"
    role="region"
    aria-labelledby="chat-cost-disclaimer-title"
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <h2
          id="chat-cost-disclaimer-title"
          class="text-base font-medium text-base-content tracking-tight"
        >
          Chat uses your model providers
        </h2>
        <p class="text-sm text-base-content/80 leading-relaxed">
          The assistant can run tools that trigger work in your workspace such
          as evals, prompt optimization, synthetic data generation, RAG, or
          other AI-backed workflows.
        </p>
        <p class="text-sm text-base-content/80 leading-relaxed">
          Those actions may call model providers using your configured API keys
          and <span class="font-medium text-base-content"
            >can incur usage charges</span
          >
          from those providers.
        </p>
      </div>
      <div
        class="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2 pt-0.5"
      >
        <button
          type="button"
          class="btn btn-primary btn-sm sm:min-w-[200px]"
          on:click={acknowledge}
        >
          I understand
        </button>
      </div>
    </div>
  </div>
{/if}

<script lang="ts">
  import { createEventDispatcher } from "svelte"
  import Dialog from "$lib/ui/dialog.svelte"
  import type { BudgetStatus } from "$lib/chat/budget_store"

  // Current budget status for the active conversation, or null when none is set
  // / nothing recorded yet.
  export let status: BudgetStatus | null = null
  // Disabled before a conversation exists (no id to key a budget by).
  export let disabled = false

  const dispatch = createEventDispatcher<{
    setbudget: { budgetUsd: number | null }
  }>()

  let dialog: Dialog
  let inputValue = ""
  let inputError: string | null = null

  $: hasBudget = status?.budget_usd != null
  $: spent = status?.spent_usd ?? 0
  $: partiallyTracked = (status?.unpriced_runs ?? 0) > 0

  function fmt(n: number): string {
    return `$${n.toFixed(2)}`
  }

  // Footer label: "Budget: $0.30 / $5.00" when set, else "Set budget".
  $: label = hasBudget
    ? `Budget: ${fmt(spent)} / ${fmt(status?.budget_usd ?? 0)}`
    : "Set budget"

  export function openExtend(): void {
    open()
  }

  function open(): void {
    if (disabled) return
    inputValue = status?.budget_usd != null ? String(status.budget_usd) : ""
    inputError = null
    dialog.show()
  }

  function save(): boolean {
    const trimmed = inputValue.trim()
    if (trimmed === "") {
      // Empty clears the budget (spend tracking continues).
      dispatch("setbudget", { budgetUsd: null })
      return true
    }
    const parsed = Number(trimmed)
    if (!Number.isFinite(parsed) || parsed < 0) {
      inputError = "Enter a non-negative dollar amount."
      return false // keep dialog open
    }
    // Guard against setting a new budget already below what's been spent — the
    // conversation would be immediately exhausted. Allowed, but warn-worthy;
    // we still permit it (the user may want to hard-stop).
    dispatch("setbudget", { budgetUsd: parsed })
    return true
  }
</script>

<button
  type="button"
  class="btn btn-ghost btn-xs text-base-content/50 hover:text-base-content/80 disabled:bg-transparent disabled:text-base-content/25"
  class:text-warning={status?.exhausted}
  on:click={open}
  {disabled}
  title="Cap the spend of operations the assistant runs in this conversation."
>
  <span aria-hidden="true">◔</span>
  {label}
  {#if partiallyTracked}
    <span
      class="ml-1 text-base-content/40"
      title="Some model calls couldn't be priced (e.g. local/custom models), so the budget only partially tracks spend."
    >
      *
    </span>
  {/if}
</button>

<Dialog
  bind:this={dialog}
  title="Conversation spend budget"
  subtitle="Cap the total cost of operations the assistant runs in this conversation — evals, data generation, task runs. These bill to your own model providers."
  action_buttons={[
    { label: "Cancel", isCancel: true },
    { label: "Save", isPrimary: true, action: save },
  ]}
>
  <div class="flex flex-col gap-3">
    <label class="form-control w-full">
      <span class="label-text text-sm mb-1">Budget (USD)</span>
      <input
        type="number"
        min="0"
        step="0.01"
        inputmode="decimal"
        placeholder="e.g. 5.00 — leave empty for no cap"
        class="input input-bordered w-full"
        bind:value={inputValue}
      />
    </label>
    {#if inputError}
      <p class="text-xs text-error">{inputError}</p>
    {/if}
    {#if status}
      <div class="text-xs text-base-content/60">
        Spent so far: {fmt(spent)}
        {#if partiallyTracked}
          <span class="block mt-1">
            Note: {status.unpriced_runs} model call{status.unpriced_runs === 1
              ? ""
              : "s"} couldn't be priced (e.g. local/custom models), so the tracked
            total may be lower than the real cost.
          </span>
        {/if}
      </div>
    {/if}
    <p class="text-xs text-base-content/50">
      Once the budget is reached, the assistant stops running new operations
      until you extend it. A long operation already running stops between steps.
    </p>
  </div>
</Dialog>

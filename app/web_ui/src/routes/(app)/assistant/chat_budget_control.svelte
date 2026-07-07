<script lang="ts">
  import Dialog from "$lib/ui/dialog.svelte"
  import type { BudgetStatus } from "$lib/chat/budget_store"

  // Current budget status for the active conversation, or null when none is set
  // / nothing recorded yet.
  export let status: BudgetStatus | null = null
  // Disabled before a conversation exists (no id to key a budget by).
  export let disabled = false

  // Caller persists the value and reports success/failure so we can keep the
  // dialog open and surface an error on failure.
  export let onSetBudget: (
    budgetUsd: number | null,
  ) => Promise<{ ok: boolean; error?: string }> = async () => ({ ok: true })

  let dialog: Dialog
  // Bound to <input type="number">, so Svelte writes back a `number` (or `null`
  // when the field is cleared) — NOT a string. Must be typed accordingly.
  let inputValue: number | null = null
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
    inputValue = status?.budget_usd ?? null
    inputError = null
    dialog.show()
  }

  // Returns whether the dialog should close. Keeps it open (surfacing an error)
  // on invalid input or a failed persist, so failures aren't silently swallowed.
  async function save(): Promise<boolean> {
    inputError = null
    // Empty field → null → clear the budget (spend tracking continues).
    if (
      inputValue !== null &&
      (!Number.isFinite(inputValue) || inputValue < 0)
    ) {
      inputError = "Enter a non-negative dollar amount."
      return false
    }
    const result = await onSetBudget(inputValue)
    if (!result.ok) {
      inputError =
        result.error ?? "Couldn't update the budget. Please try again."
      return false
    }
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
    { label: "Save", isPrimary: true, asyncAction: save },
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

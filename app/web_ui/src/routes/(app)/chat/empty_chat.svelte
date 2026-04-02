<script lang="ts">
  // TODO: Wire this up: each button has a data-prompt attribute.
</script>

<div class="kc-empty-state">
  <!-- Header -->
  <div class="kc-header">
    <div class="kc-icon">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path
          d="M14 3C14 3 6 8 6 16C6 20.4 9.6 24 14 24C18.4 24 22 20.4 22 16C22 8 14 3 14 3Z"
          fill="white"
          opacity="0.95"
        />
        <path
          d="M14 10C14 10 10 13 10 17C10 19.2 11.8 21 14 21C16.2 21 18 19.2 18 17C18 13 14 10 14 10Z"
          fill="#D85A30"
          opacity="0.7"
        />
      </svg>
    </div>
    <h1>What are you optimizing?</h1>
    <p>I know your tasks, evals, and data. Tell me what to improve.</p>
  </div>

  <!-- Primary suggestions (2x2) -->
  <div class="kc-grid-primary">
    <button
      class="kc-card"
      data-prompt="Help me improve the quality of my task outputs"
    >
      <span class="kc-card-icon">◆</span>
      <div>
        <span class="kc-card-title">Improve quality</span>
        <span class="kc-card-subtitle">Better outputs from my task</span>
      </div>
    </button>

    <button
      class="kc-card"
      data-prompt="Help me reduce costs for running my task"
    >
      <span class="kc-card-icon">↓</span>
      <div>
        <span class="kc-card-title">Cut costs</span>
        <span class="kc-card-subtitle">Cheaper models or fine-tuning</span>
      </div>
    </button>

    <button
      class="kc-card"
      data-prompt="Help me make my task faster with lower latency"
    >
      <span class="kc-card-icon">⚡</span>
      <div>
        <span class="kc-card-title">Speed it up</span>
        <span class="kc-card-subtitle">Lower latency, faster runs</span>
      </div>
    </button>

    <button
      class="kc-card"
      data-prompt="Help me create an eval to measure and improve my AI system"
    >
      <span class="kc-card-icon">✓</span>
      <div>
        <span class="kc-card-title">Build an eval</span>
        <span class="kc-card-subtitle">Measure what matters</span>
      </div>
    </button>
  </div>

  <!-- Secondary suggestions (3-col pills) -->
  <div class="kc-grid-secondary">
    <button
      class="kc-pill"
      data-prompt="Help me run this task on-prem or with a local model"
      >Run on-prem</button
    >
    <button
      class="kc-pill"
      data-prompt="Help me generate synthetic training data for my task"
      >Synthetic data</button
    >
    <button
      class="kc-pill"
      data-prompt="Help me fine-tune a model for my use case">Fine-tune</button
    >
  </div>

  <!-- Footer -->
  <p class="kc-footer">
    Or just ask — I can work with any task in your project.
  </p>
</div>

<style>
  /* ============================================================
     Kiln Chat Empty State
     ============================================================
     Design spec for the new-chat landing screen.
     
     INTEGRATION NOTES:
     - Replace CSS custom properties with your design system tokens
     - Wire onSuggestionClick(prompt) to your chat input handler
     - The flame icon SVG can be swapped for the real Kiln logo
     - All hover states use CSS only (no JS needed)
     ============================================================ */

  :root {
    --kc-text-primary: #1a1a1a;
    --kc-text-secondary: #6b6b6b;
    --kc-text-tertiary: #9a9a9a;
    --kc-bg-primary: #ffffff;
    --kc-bg-hover: #f7f7f5;
    --kc-border: rgba(0, 0, 0, 0.1);
    --kc-border-hover: rgba(0, 0, 0, 0.2);
    --kc-radius: 12px;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --kc-text-primary: #ececec;
      --kc-text-secondary: #a0a0a0;
      --kc-text-tertiary: #6b6b6b;
      --kc-bg-primary: #1e1e1e;
      --kc-bg-hover: #2a2a2a;
      --kc-border: rgba(255, 255, 255, 0.1);
      --kc-border-hover: rgba(255, 255, 255, 0.2);
    }
  }

  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--kc-bg-primary);
    color: var(--kc-text-primary);
  }

  .kc-empty-state {
    max-width: 560px;
    margin: 3rem auto;
    padding: 0 1rem;
  }

  /* ---- Header ---- */

  .kc-header {
    text-align: center;
    margin-bottom: 2.5rem;
  }

  .kc-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 56px;
    height: 56px;
    border-radius: 12px;
    background: linear-gradient(135deg, #ef9f27, #d85a30);
    margin-bottom: 1rem;
  }

  .kc-header h1 {
    font-size: 22px;
    font-weight: 500;
    margin-bottom: 8px;
  }

  .kc-header p {
    font-size: 14px;
    color: var(--kc-text-secondary);
    line-height: 1.5;
  }

  /* ---- Primary suggestion cards (2x2 grid) ---- */

  .kc-grid-primary {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 8px;
  }

  .kc-card {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 14px 16px;
    border-radius: var(--kc-radius);
    border: 0.5px solid var(--kc-border);
    background: var(--kc-bg-primary);
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s;
    text-align: left;
    font-family: inherit;
    color: inherit;
    outline: none;
  }

  .kc-card:hover,
  .kc-card:focus-visible {
    border-color: var(--kc-border-hover);
    background: var(--kc-bg-hover);
  }

  .kc-card-icon {
    font-size: 16px;
    line-height: 1;
    margin-top: 1px;
    flex-shrink: 0;
  }

  .kc-card-title {
    font-size: 14px;
    font-weight: 500;
    line-height: 1.3;
    display: block;
  }

  .kc-card-subtitle {
    font-size: 12px;
    color: var(--kc-text-tertiary);
    line-height: 1.4;
    display: block;
    margin-top: 2px;
  }

  /* ---- Secondary suggestion pills (3-col) ---- */

  .kc-grid-secondary {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin-bottom: 2rem;
  }

  .kc-pill {
    text-align: center;
    padding: 10px 8px;
    border-radius: var(--kc-radius);
    border: 0.5px solid var(--kc-border);
    background: var(--kc-bg-primary);
    font-size: 13px;
    font-family: inherit;
    color: var(--kc-text-secondary);
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s,
      color 0.15s;
    outline: none;
  }

  .kc-pill:hover,
  .kc-pill:focus-visible {
    border-color: var(--kc-border-hover);
    background: var(--kc-bg-hover);
    color: var(--kc-text-primary);
  }

  /* ---- Footer ---- */

  .kc-footer {
    text-align: center;
    font-size: 12px;
    color: var(--kc-text-tertiary);
  }
</style>

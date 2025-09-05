<script lang="ts">
  import {
    app_version,
    update_update_store,
    update_info,
  } from "$lib/utils/update"
  import AppPage from "../../app_page.svelte"
  import { onMount } from "svelte"

  onMount(() => {
    update_update_store()
  })
</script>

<AppPage
  title="Check for Update"
  sub_subtitle={`Current Version ${app_version}`}
  breadcrumbs={[{ label: "Settings", href: "/settings" }]}
>
  <div class="max-w-2xl">
    {#if $update_info.update_loading}
      <!-- Loading State -->
      <div class="card bg-base-100 shadow-lg border border-base-300">
        <div class="card-body items-center text-center py-16">
          <div class="loading loading-spinner loading-lg"></div>
          <h3 class="card-title mt-4">Checking for Updates</h3>
          <p class="text-base-content/70">
            Please wait while we check for the latest version...
          </p>
        </div>
      </div>
    {:else if $update_info.update_result && $update_info.update_result.has_update}
      <!-- Update Available -->
      <div class="card bg-base-100 shadow-lg border border-success/20">
        <div class="card-body">
          <div class="flex items-center gap-3 mb-4">
            <div class="bg-success/10 p-3 rounded-full">
              <svg
                class="w-6 h-6 text-success"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"
                />
              </svg>
            </div>
            <div>
              <h2 class="card-title text-success">Update Available</h2>
              <p class="text-base-content/70">
                A new version of Kiln is ready to download
              </p>
            </div>
          </div>

          <div class="bg-base-200 p-4 rounded-lg mb-6">
            <div class="flex justify-between items-center">
              <div>
                <div class="text-sm font-medium text-base-content/70">
                  Current Version
                </div>
                <div class="font-mono text-lg">{app_version}</div>
              </div>
              <div class="text-2xl text-base-content/30">→</div>
              <div>
                <div class="text-sm font-medium text-base-content/70">
                  Latest Version
                </div>
                <div class="font-mono text-lg text-success">
                  {$update_info.update_result.latest_version}
                </div>
              </div>
            </div>
          </div>

          <div class="card-actions justify-end">
            <button
              class="btn btn-outline"
              on:click={() => update_update_store()}
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Check Again
            </button>
            <a
              href={$update_info.update_result.link}
              class="btn btn-success gap-2"
              target="_blank"
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"
                />
              </svg>
              Download Update
            </a>
          </div>
        </div>
      </div>
    {:else if $update_info.update_result && !$update_info.update_result.has_update}
      <!-- No Update Available -->
      <div class="card bg-base-100 shadow-lg border border-base-300">
        <div class="card-body">
          <div class="flex items-center gap-3 mb-4">
            <div class="bg-primary/10 p-3 rounded-full">
              <svg
                class="w-6 h-6 text-primary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div>
              <h2 class="card-title text-primary">You're Up to Date</h2>
              <p class="text-base-content/70">
                You are using the latest version of Kiln
              </p>
            </div>
          </div>

          <div class="bg-base-200 p-4 rounded-lg mb-6">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-medium text-base-content/70">
                  Current Version
                </div>
                <div class="font-mono text-lg">{app_version}</div>
              </div>
              <div class="badge badge-primary badge-outline">Latest</div>
            </div>
          </div>

          <div class="card-actions justify-end">
            <button
              class="btn btn-outline"
              on:click={() => update_update_store()}
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Check Again
            </button>
          </div>
        </div>
      </div>
    {:else}
      <!-- Error State -->
      <div class="card bg-base-100 shadow-lg border border-error/20">
        <div class="card-body">
          <div class="flex items-center gap-3 mb-4">
            <div class="bg-error/10 p-3 rounded-full">
              <svg
                class="w-6 h-6 text-error"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div>
              <h2 class="card-title text-error">Error Checking for Update</h2>
              <p class="text-base-content/70">
                We couldn't check for updates at this time
              </p>
            </div>
          </div>

          {#if $update_info.update_error?.message}
            <div class="alert alert-error mb-4">
              <svg
                class="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>{$update_info.update_error.message}</span>
            </div>
          {/if}

          <div class="card-actions justify-end">
            <button
              class="btn btn-outline"
              on:click={() => update_update_store()}
            >
              <svg
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              Try Again
            </button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</AppPage>

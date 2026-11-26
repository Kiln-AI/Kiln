// Test support only; never import this from app code.

type SvelteModule = typeof import("svelte")

/**
 * A `vi.mock("svelte", ...)` factory for component tests that need onMount.
 * Vitest resolves "svelte" to its server build, whose onMount never runs; this
 * swaps in the browser runtime's onMount.
 */
export async function browser_svelte(
  importOriginal: <T>() => Promise<T>,
): Promise<SvelteModule> {
  const actual = await importOriginal<SvelteModule>()
  // svelte/internal ships no type declarations.
  const internal_path: string = "svelte/internal"
  const internal = (await import(/* @vite-ignore */ internal_path)) as Pick<
    SvelteModule,
    "onMount"
  >
  return {
    ...actual,
    // @testing-library/svelte probes these Svelte 5 only exports to pick a mount strategy.
    mount: undefined,
    untrack: undefined,
    onMount: internal.onMount,
  } as SvelteModule
}

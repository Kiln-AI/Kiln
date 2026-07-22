// Vitest stand-in for SvelteKit's `$env/dynamic/public`, which needs the
// SvelteKit runtime and throws when imported in unit tests. Wired up via the
// test alias in vite.config.ts. Empty env = every PUBLIC_ flag reads as off.
export const env: Record<string, string | undefined> = {}

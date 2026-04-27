---
status: complete
---

# Phase 1: `sessionStorageStore` Utility

## Goal

Add a `sessionStorageStore<T>()` function to `app/web_ui/src/lib/stores/local_storage_store.ts` that mirrors the existing `localStorageStore` pattern but is backed by `sessionStorage` instead of `localStorage`.

## Implementation

### Changes to `local_storage_store.ts`

Add `sessionStorageStore<T>(key: string, initialValue: T)` below the existing `localStorageStore`. The function:

1. Checks for browser environment via `typeof window !== "undefined" && window.sessionStorage`
2. Restores persisted value from `sessionStorage` on creation (falls back to `initialValue` if missing or corrupt)
3. Subscribes to store changes and writes to `sessionStorage` on each update
4. Guards against oversized values (>1MB) with a console error and skipped write
5. Returns a standard Svelte `Writable<T>` store

The implementation is intentionally parallel to `localStorageStore` — same structure, same size guard, same SSR safety check — just targeting `sessionStorage`.

## Tests

### New file: `app/web_ui/src/lib/stores/local_storage_store.test.ts`

Tests for both `localStorageStore` and `sessionStorageStore`:

- **Restore from storage**: Pre-populate storage, create store, verify initial value matches stored data
- **Falls back to initialValue**: No stored data, verify store uses provided default
- **Saves on update**: Create store, call `set()`, verify storage was written
- **Handles corrupt JSON**: Pre-populate storage with invalid JSON, verify store falls back to initialValue without throwing
- **Size guard**: Set a value larger than 1MB, verify storage write is skipped and error is logged
- **SSR safety**: When `window` is undefined, store uses initialValue and does not throw
- **Independent keys**: Two stores with different keys do not interfere with each other

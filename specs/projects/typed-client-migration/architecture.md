---
status: complete
---

# Architecture: Typed Client Migration

## Approach

This is a mechanical refactor — no new components, no new patterns. Each `fetch()` call is replaced with the equivalent `client.GET()` or `client.POST()` call using the existing typed client infrastructure.

## Pattern

### Before (fetch)

```typescript
let res = await fetch(base_url + "/api/some/endpoint", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
})
let data = await res.json()
if (res.status !== 200) { /* error */ }
```

### After (typed client)

```typescript
const { data, error } = await client.POST("/api/some/endpoint", {
  body: payload,
})
if (error) { /* error — access error.message, error.detail, etc. */ }
```

Key differences:
- No manual `JSON.stringify` / `res.json()` — the client handles serialization
- No manual headers — the client sets `Content-Type`
- Error is returned as `{ error }` not via status codes
- `base_url` is already configured in the client

## Import Changes

Files currently import `base_url` from `$lib/api_client`. After migration:
- If `base_url` is still used elsewhere in the file: keep it, add `client` import
- If `base_url` is no longer used: replace with `client` import

## Testing Strategy

- Run `npm run check` (TypeScript) to verify type correctness
- Manual verification that the three call sites compile and the typed client paths resolve
- No new tests needed — this is a 1:1 behavioral replacement with existing test coverage

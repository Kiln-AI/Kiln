# Backlog: Jev Provider (TypeSafe AI System One)

Items found while implementing, outside the phase that found them. Phase 9 reviews these
with the user and closes or dismisses each one.

## Open

- **Confirm `GET https://api.typesafe.ai/v1/models` rejects a bad key.** This is the
  precondition `architecture.md` sets for `connect_typesafe`. It could not be verified
  during Phase 1 because sandbox egress to `api.typesafe.ai` is proxy-blocked, so the
  phase took the GET branch on indirect evidence from the official SDK only. If the
  endpoint turns out to be public — as Featherless's `/v1/models` is, which is why
  `connect_featherless` uses a minimal POST — then `connect_typesafe` will store any
  arbitrary string as a valid key and report "Connected to TypeSafe AI", and the user
  will discover the bad key only on their first run. In that case, switch to the spec's
  minimal `POST /v1/systemone` fallback. Needs a human with a live key; must not reach
  merge unresolved.

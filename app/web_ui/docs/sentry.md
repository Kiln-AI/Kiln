# Sentry — web UI

Frontend errors flow to Sentry project `kiln-oy/frontend`. This doc covers how
the wiring works and how to drive it manually. The desktop server side is
documented separately in
[`app/desktop/docs/sentry.md`](../../desktop/docs/sentry.md); both sides
share the same `SENTRY_ENV_NAME` / `SENTRY_RELEASE_TAG` job-level env vars in
CI so a single build lands under matching environment + release tags across
the two Sentry projects.

## Files involved

- `src/hooks.client.ts` — initializes the Sentry SDK in the browser and exports
  `handleError` so SvelteKit forwards lifecycle errors to Sentry.
- `vite.config.ts` — runs `sentrySvelteKit` at build time to upload source maps.
- `.github/workflows/build_desktop.yml` and `windows_release_build.yml` — pass
  the env vars listed below into the desktop build.

## Environments and release names

The frontend reports under one of two environments:

| Trigger                              | Environment  | Release name                        |
| ------------------------------------ | ------------ | ----------------------------------- |
| GitHub Release created               | `production` | `kiln-studio-web@<git-tag>`         |
| Push to `main` / `workflow_dispatch` | `staging`    | `kiln-studio-web@<full-commit-sha>` |

Both values are passed as build-time env vars (`VITE_KILN_SENTRY_ENV` and
`VITE_KILN_SENTRY_RELEASE`) and inlined into the bundle so runtime events
match what was uploaded at build time.

Each build produces source maps that are uniquely paired to that build by two
keys: the release name (e.g. `kiln-studio-web@<sha-A>`) and a per-file debug
ID embedded in both the JS and its matching map. Sentry uses the debug ID to
pair an incoming error to a source map; the release name is the secondary
key. Different versions never cross-contaminate — build A's maps will never
be used to symbolicate build B's errors, even if the two are uploaded back to
back.

## Why an auth token is required

The vite plugin uploads two things during `npm run build`:

1. The compiled JS source maps for that build.
2. A small per-file UUID ("debug ID") embedded in both the JS and the matching
   source map. At runtime, errors carry the debug ID, and Sentry pairs them
   with the corresponding map.

Both uploads happen against the Sentry API, which needs `SENTRY_AUTH_TOKEN`
(scopes: `org:ci`). Without it, the plugin no-ops and
errors will still arrive in Sentry but with minified stack traces (which
are not great for debugging).

The token lives in the GitHub repo secret `SENTRY_AUTH_TOKEN`.

## Workflows

### Production release

1. Cut a GitHub release. The tag (e.g. `v0.28.0`) is what appears in Sentry.
2. `windows_release_build.yml` and `build_desktop.yml` both fire on the
   release event and upload source maps tagged with `environment=production`.
3. In Sentry, filter on `environment:production` and the relevant release name.

### Push to main / ad-hoc staging build

1. Any push to `main` triggers `build_desktop.yml`.
2. Source maps upload under `kiln-studio-web@<full-sha>`, environment
   `staging`. Useful for catching dogfooding errors before release.
3. `workflow_dispatch` (manual run) behaves the same as a `main` push.

### Dev server

`npm run dev` does not initialize Sentry — `Sentry.init` is gated on
`VITE_KILN_SENTRY_DSN` being set, and the dev environment leaves it unset.
Errors stay local; nothing is uploaded.

If you ever need it on (rare), run dev with the DSN set:

```
VITE_KILN_SENTRY_DSN=https://...@o.../... npm run dev
```

But note: dev builds have no debug IDs, so any events sent will have minified traces.

## CI env vars reference

Set on the build steps in both workflow files:

| Variable                   | Source                      | Purpose                                             |
| -------------------------- | --------------------------- | --------------------------------------------------- |
| `SENTRY_AUTH_TOKEN`        | repo secret                 | Authenticates source map upload                     |
| `SENTRY_ORG`               | hardcoded `kiln-oy`         | Sentry org slug                                     |
| `SENTRY_PROJECT`           | hardcoded `frontend`        | Sentry project slug                                 |
| `VITE_KILN_SENTRY_DSN`     | hardcoded DSN               | Gates `Sentry.init` — unset = no-op, no events sent |
| `VITE_KILN_SENTRY_ENV`     | `production` or `staging`   | Sentry environment tag                              |
| `VITE_KILN_SENTRY_RELEASE` | `kiln-studio-web@<tag/sha>` | Sentry release name (must match upload + runtime)   |

## Running with Sentry locally

Useful when changing anything in `hooks.client.ts`, `vite.config.ts`, or the
workflow env blocks, and you want to verify the wiring before pushing.

1. Create a Sentry auth token with `org:ci` scope.
2. From the repo root, run a production build with the token plus a
   throwaway environment + release name so events don't collide with real
   `production` / `staging` data:

   ```
   SENTRY_AUTH_TOKEN='sntrys_...' SENTRY_ORG=kiln-oy SENTRY_PROJECT=frontend \
     VITE_KILN_SENTRY_DSN='https://...@o.../...' \
     VITE_KILN_SENTRY_ENV=local \
     VITE_KILN_SENTRY_RELEASE="kiln-studio-web@local-$(git rev-parse --short HEAD)" \
     npm run build --prefix app/web_ui && \
     npm run preview --prefix app/web_ui -- --port 5173
   ```

   The source map upload happens during `npm run build` — the
   `sentrySvelteKit` vite plugin runs as a post-build step and pushes the
   maps to Sentry once the bundle is emitted. Look for
   `[sentry-vite-plugin] Info: Successfully uploaded source maps to Sentry`
   near the end of the build log to confirm. The `npm run preview` step is
   just a static file server for the already-built bundle.

3. Open <http://localhost:5173> and trigger an error somewhere in the app.
   In Sentry, filter on `environment:local` to find your event with a fully
   symbolicated stack trace.

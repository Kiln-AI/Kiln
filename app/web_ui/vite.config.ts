import { readFileSync } from "node:fs"
import { sentrySvelteKit } from "@sentry/sveltekit"
import { sveltekit } from "@sveltejs/kit/vite"
import { defineConfig } from "vitest/config"

// The Sentry release name must match the value sent at runtime from
// hooks.client.ts so uploaded source maps map back to incoming events.
// CI overrides VITE_KILN_SENTRY_RELEASE for non-release builds (commit SHA);
// for releases and local builds we fall back to the app version, which is
// also imported by src/lib/utils/update.ts so both stay in sync.
const appVersion = readFileSync("./src/lib/version", "utf-8").trim()
const sentryRelease =
  process.env.VITE_KILN_SENTRY_RELEASE || `kiln-studio-web@${appVersion}`

const sentryPlugin = process.env.SENTRY_AUTH_TOKEN
  ? sentrySvelteKit({
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: { name: sentryRelease },
    })
  : null

export default defineConfig({
  plugins: [...(sentryPlugin ? [sentryPlugin] : []), sveltekit()],
  optimizeDeps: {
    // CodeMirror is a set of packages that share one runtime: @codemirror/view,
    // /language, /commands and /lang-python all build their extensions out of
    // Facet and StateField from @codemirror/state, and EditorState.create()
    // validates them with instanceof. Two copies of @codemirror/state in a page
    // is therefore not "slightly wasteful", it is fatal - every extension made
    // by one copy is unrecognizable to the other, and the editor dies with
    // "Unrecognized extension value in extension set".
    //
    // Dev can produce those two copies. code_editor.svelte imports all five
    // lazily, so if the dep optimizer's committed metadata does not already
    // contain them - a server that has been up since before this component
    // existed, a branch switch, an npm install, anything that leaves the
    // running optimizer's idea of the dep set behind the source - they are
    // DISCOVERED at request time instead. Discovery re-runs the optimizer,
    // which rewrites node_modules/.vite/deps with a different chunk split and a
    // new browser hash, and the packages that were already optimized keep being
    // served from the old generation while the newly discovered ones come from
    // the new one. Both generations put @codemirror/state in a chunk, so the
    // page ends up loading e.g. chunk-VPD6HJ22.js?v=<old> and the same file
    // again under ?v=<new>, which are two module URLs and therefore two live
    // copies. Vite's recovery for this is a full page reload pushed over the
    // HMR websocket; on a long-lived dev server that socket is exactly the
    // thing that has quietly died, and then the breakage sticks until someone
    // restarts the server. That is the folklore fix we kept repeating.
    //
    // Naming them here takes the optimizer's decision away from the scanner.
    // They are pre-bundled from config at every server start whether or not
    // anything imports them yet, so there is no request-time discovery, no
    // re-run, no second generation, and no reload to miss. It also changes the
    // config hash, so a cache written before this lands is discarded rather
    // than reused. Anything added to the CodeMirror set later belongs in this
    // list too - a package left off is a package that can be discovered late.
    //
    // Dev only: production has no dep optimizer. Rollup resolves
    // @codemirror/state to one file and emits it once.
    include: [
      "@codemirror/commands",
      "@codemirror/lang-python",
      "@codemirror/language",
      "@codemirror/state",
      "@codemirror/view",
    ],
  },
  test: {
    include: ["src/**/*.{test,spec}.{js,ts}"],
  },
})

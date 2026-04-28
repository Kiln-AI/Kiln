import * as Sentry from "@sentry/sveltekit"

import { app_version } from "$lib/utils/update"

// init without the DSN will result in a no-op, not a crash
Sentry.init({
  dsn: import.meta.env.VITE_KILN_SENTRY_DSN,
  release:
    import.meta.env.VITE_KILN_SENTRY_RELEASE ||
    `kiln-studio-web@${app_version}`,
  environment: import.meta.env.VITE_KILN_SENTRY_ENV || "unknown",
  sendDefaultPii: false,
  tracesSampleRate: 0.1,
  tracePropagationTargets: ["localhost"],
})

export const handleError = Sentry.handleErrorWithSentry()

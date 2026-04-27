import * as Sentry from "@sentry/sveltekit"

import { app_version } from "$lib/utils/update"

if (import.meta.env.VITE_KILN_ENABLE_SENTRY === "1") {
  Sentry.init({
    dsn: "https://667db4eeb7ae7f46e960fee790d836a8@o4511151852224512.ingest.de.sentry.io/4511276081545296",
    release:
      import.meta.env.VITE_KILN_SENTRY_RELEASE ||
      `kiln-studio-web@${app_version}`,
    environment: import.meta.env.VITE_KILN_SENTRY_ENV || import.meta.env.MODE,
    sendDefaultPii: false,
    tracesSampleRate: 0.1,
    tracePropagationTargets: ["localhost"],
  })
}

export const handleError = Sentry.handleErrorWithSentry()

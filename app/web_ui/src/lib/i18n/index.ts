import { derived } from "svelte/store"
import { localStorageStore } from "$lib/stores/local_storage_store"
import { translate, localeNames, type SupportedLocale } from "./translations"

// Derive supported locales from localeNames (single source of truth)
const supportedLocales = new Set<string>(Object.keys(localeNames))

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === "string" && supportedLocales.has(value)
}

/**
 * Sanitize the persisted locale value in localStorage before
 * localStorageStore reads it. This prevents localStorageStore from
 * returning an invalid locale if the stored value is malformed or
 * unsupported — it independently calls JSON.parse on the raw value.
 */
function sanitizePersistedLocale(): SupportedLocale {
  const isBrowser = typeof window !== "undefined"
  const fallback: SupportedLocale = "en"

  if (!isBrowser) {
    return fallback
  }

  const raw = localStorage.getItem("kiln_locale")
  if (raw !== null) {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (isSupportedLocale(parsed)) {
        return parsed
      }
    } catch {
      // Malformed JSON — fall through
    }
    // Stored value is invalid; remove it so localStorageStore uses our default
    localStorage.removeItem("kiln_locale")
    return fallback
  }

  // No stored value — auto-detect from browser language
  const browserLang = navigator.language.split("-")[0]
  if (isSupportedLocale(browserLang)) {
    return browserLang
  }
  return fallback
}

/**
 * The user's selected locale, persisted in localStorage.
 * Defaults to English. Auto-detects browser language on first load.
 */
export const locale = localStorageStore<SupportedLocale>(
  "kiln_locale",
  sanitizePersistedLocale(),
)

/**
 * Reactive translation function.
 * Usage in Svelte components: `$t('nav.run')`
 */
export const t = derived(locale, ($locale) => {
  return (key: string): string => translate($locale, key)
})

export { localeNames, type SupportedLocale } from "./translations"

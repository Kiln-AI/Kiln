import { derived } from "svelte/store"
import { localStorageStore } from "$lib/stores/local_storage_store"
import { translate, localeNames, type SupportedLocale } from "./translations"

// Derive supported locales from localeNames (single source of truth)
const supportedLocales = new Set<string>(Object.keys(localeNames))

function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === "string" && supportedLocales.has(value)
}

/**
 * The user's selected locale, persisted in localStorage.
 * Defaults to English. Auto-detects browser language on first load.
 */
function createLocaleStore() {
  const isBrowser = typeof window !== "undefined"
  let initialLocale: SupportedLocale = "en"

  if (isBrowser) {
    const stored = localStorage.getItem("kiln_locale")
    if (stored) {
      try {
        const parsed: unknown = JSON.parse(stored)
        if (isSupportedLocale(parsed)) {
          initialLocale = parsed
        }
      } catch {
        // Ignore malformed persisted value; fall through to browser detection
      }
    } else {
      // Auto-detect from browser language
      const browserLang = navigator.language.split("-")[0]
      if (isSupportedLocale(browserLang)) {
        initialLocale = browserLang
      }
    }
  }

  return localStorageStore<SupportedLocale>("kiln_locale", initialLocale)
}

export const locale = createLocaleStore()

/**
 * Reactive translation function.
 * Usage in Svelte components: `$t('nav.run')`
 */
export const t = derived(locale, ($locale) => {
  return (key: string): string => translate($locale, key)
})

export { localeNames, type SupportedLocale } from "./translations"

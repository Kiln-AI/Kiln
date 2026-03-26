import { derived } from "svelte/store"
import { localStorageStore } from "$lib/stores/local_storage_store"
import { translate, type SupportedLocale } from "./translations"

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
      initialLocale = JSON.parse(stored) as SupportedLocale
    } else {
      // Auto-detect from browser language
      const browserLang = navigator.language.split("-")[0]
      const supported: SupportedLocale[] = ["en", "es", "zh", "ja", "ko", "fr", "de", "pt"]
      if (supported.includes(browserLang as SupportedLocale)) {
        initialLocale = browserLang as SupportedLocale
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

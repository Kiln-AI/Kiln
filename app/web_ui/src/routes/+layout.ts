import "../lib/i18n"
import { browser } from "$app/environment"
import { locale, waitLocale } from "svelte-i18n"
import posthog from "posthog-js"
import { dev } from "$app/environment"

export const prerender = true
export const ssr = false

export const load = async () => {
  if (browser && !dev) {
    posthog.init("phc_pdNulYUFOFmRcgeQkYCOAiCQiZOC4VP8npDtRkNSirw", {
      api_host: "https://us.i.posthog.com",
      person_profiles: "identified_only",
      capture_pageview: false,
      capture_pageleave: false,
    })
  }
  if (browser) {
    const savedLocale = localStorage.getItem("locale")
    if (savedLocale) {
      locale.set(savedLocale)
    }
  }
  await waitLocale()
}

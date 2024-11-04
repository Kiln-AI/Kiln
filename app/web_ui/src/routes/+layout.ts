import posthog from "posthog-js"
import { browser } from "$app/environment"
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
  return
}

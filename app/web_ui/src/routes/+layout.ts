import posthog from "posthog-js"
import { browser } from "$app/environment"
import { dev } from "$app/environment"

export const prerender = true
export const ssr = false

export const load = async () => {
  if (browser && !dev) {
    posthog.init("phc_pdNulYUFOFmRcgeQkYCOAiCQiZOC4VP8npDtRkNSirw", {
      api_host: "https://ustat.getkiln.ai",
      person_profiles: "always",
      capture_pageview: false,
      capture_pageleave: false,
      autocapture: false,
    })
  }
  return
}

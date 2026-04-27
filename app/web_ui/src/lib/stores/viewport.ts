import { readable, derived, type Readable } from "svelte/store"
import { browser } from "$app/environment"

export const viewportWidth: Readable<number> = readable(
  browser ? window.innerWidth : 0,
  (set) => {
    if (!browser) return
    const onResize = () => set(window.innerWidth)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  },
)

export const isLg: Readable<boolean> = derived(viewportWidth, (w) => w >= 1024)

export const isNarrowViewport: Readable<boolean> = derived(
  viewportWidth,
  (w) => w < 1550,
)

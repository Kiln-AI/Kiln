import { writable } from "svelte/store"
import { browser } from "$app/environment"
import {
  getChatBarExpanded,
  setChatBarExpanded as persistChatBarExpanded,
} from "$lib/chat/chat_ui_storage"

const initial = browser ? getChatBarExpanded() : true

export const chatBarExpanded = writable<boolean>(initial)

export function setChatBarExpanded(expanded: boolean): void {
  chatBarExpanded.set(expanded)
  if (browser) {
    persistChatBarExpanded(expanded)
  }
}

export const CHAT_BAR_MIN_WIDTH = 280
export const CHAT_BAR_MAX_WIDTH_VW = 30
export const CHAT_BAR_DEFAULT_WIDTH_LG = 320
export const CHAT_BAR_DEFAULT_WIDTH_2XL = 380
export const CHAT_BAR_BREAKPOINT_2XL = 1536

export function getChatBarMaxWidth(viewportWidth: number): number {
  return Math.floor(viewportWidth * (CHAT_BAR_MAX_WIDTH_VW / 100))
}

export function clampChatBarWidth(
  width: number,
  viewportWidth: number,
): number {
  const max = getChatBarMaxWidth(viewportWidth)
  return Math.round(Math.max(CHAT_BAR_MIN_WIDTH, Math.min(width, max)))
}

export function getChatBarDefaultWidth(viewportWidth: number): number {
  if (viewportWidth >= CHAT_BAR_BREAKPOINT_2XL) {
    return CHAT_BAR_DEFAULT_WIDTH_2XL
  }
  return CHAT_BAR_DEFAULT_WIDTH_LG
}

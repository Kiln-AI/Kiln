import { env } from "$env/dynamic/public"

const base = env.PUBLIC_CHAT_API_URL?.trim()
export const CHAT_API_URL = base
  ? base.replace(/\/$/, "") + "/api/chat"
  : "http://127.0.0.1:8000/api/chat"

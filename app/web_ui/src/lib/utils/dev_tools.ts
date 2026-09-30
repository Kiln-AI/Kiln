import { env } from "$env/dynamic/public"

// Feature flag: developer-only assistant affordances (the copy-conversation-id
// widget) only render when PUBLIC_ENABLE_DEV_TOOLS is explicitly "true".
// See .env.example.
export const dev_tools_enabled = env.PUBLIC_ENABLE_DEV_TOOLS === "true"

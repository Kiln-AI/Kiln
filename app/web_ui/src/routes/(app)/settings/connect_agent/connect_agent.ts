import { dev } from "$app/environment"
import { base_url } from "$lib/api_client"

const DEFAULT_PORT = "8757"
// The address that docs/agent_install.md and the Kiln skill are written with.
export const DEFAULT_ORIGIN = `http://localhost:${DEFAULT_PORT}`
export const MCP_PATH = "/mcp"
// README.md repeats BASE_PROMPT verbatim; connect_agent.test.ts fails while the two differ.
export const AGENT_INSTALL_GUIDE_URL =
  "https://raw.githubusercontent.com/Kiln-AI/Kiln/main/docs/agent_install.md"
export const BASE_PROMPT = `Install Kiln's app, skill, and MCP following the guide here: ${AGENT_INSTALL_GUIDE_URL}`

const LOOPBACK_HOSTNAMES = ["localhost", "127.0.0.1", "[::1]"]

/**
 * The origin of the Kiln server this page talks to. A production build is served
 * by the Kiln server itself, so the page origin is the server's real address. Under
 * `vite dev` the page origin is the Vite server, so the build-time API URL is used.
 */
export function app_origin(is_dev: boolean = dev): string {
  return is_dev ? base_url : window.location.origin
}

export function mcp_url(origin: string): string {
  return origin.replace(/\/+$/, "") + MCP_PATH
}

/**
 * True when the guide's `http://localhost:8757` reaches the same server as `origin`:
 * plain HTTP on the default port at a loopback host name.
 */
export function is_default_address(origin: string): boolean {
  let url: URL
  try {
    url = new URL(origin)
  } catch {
    return false
  }
  return (
    url.protocol === "http:" &&
    url.port === DEFAULT_PORT &&
    LOOPBACK_HOSTNAMES.includes(url.hostname)
  )
}

/**
 * The install prompt for an agent. Off the default address it also names the real
 * MCP server URL, because the guide can only name the default.
 */
export function build_prompt(origin: string): string {
  if (is_default_address(origin)) {
    return BASE_PROMPT
  }
  return `${BASE_PROMPT}\n\nThe Kiln MCP server is at ${mcp_url(origin)}.`
}

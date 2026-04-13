import { isGitHubUrl } from "$lib/git_sync/api"

export type AuthFormMode = "oauth" | "pat"

export function initialAuthFormMode(
  auth_mode: string | null | undefined,
  git_url: string | null | undefined,
): AuthFormMode {
  if (!git_url || !isGitHubUrl(git_url)) {
    return "pat"
  }
  return auth_mode === "github_oauth" ? "oauth" : "pat"
}

export function buildOAuthUpdatePayload(token: string): {
  oauth_token: string
  auth_mode: string
} {
  return { oauth_token: token, auth_mode: "github_oauth" }
}

export function buildPatUpdatePayload(
  token: string,
  current_auth_mode: string | null | undefined,
): { pat_token: string; auth_mode?: string } {
  // When switching away from github_oauth (or any non-pat mode) to PAT, we
  // must explicitly set auth_mode so the backend stops using the stored OAuth
  // token. For projects already on pat_token, auth_mode is omitted to keep
  // the existing PATCH semantics (token-only update).
  if (current_auth_mode === "pat_token") {
    return { pat_token: token }
  }
  return { pat_token: token, auth_mode: "pat_token" }
}

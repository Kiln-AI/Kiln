import { base_url } from "$lib/api_client"

async function request<T>(
  method: string,
  path: string,
  body: unknown,
): Promise<T> {
  const resp = await fetch(`${base_url}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(
      detail?.detail || detail?.message || `Request failed: ${resp.statusText}`,
    )
  }
  return resp.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return request("POST", path, body)
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  return request("PATCH", path, body)
}

export type TestAccessResponse = {
  success: boolean
  message: string
  auth_required: boolean
  auth_method: string | null
}

export type ListBranchesResponse = {
  branches: string[]
  default_branch: string | null
}

export type CloneResponse = {
  clone_path: string
  success: boolean
  message: string
}

export type ProjectInfo = {
  path: string
  name: string
  description: string
  id: string
}

export type ScanProjectsResponse = {
  projects: ProjectInfo[]
}

export type RenameCloneResponse = {
  new_clone_path: string
  success: boolean
  message: string
}

export type GitSyncConfigResponse = {
  sync_mode: string
  auth_mode: string
  remote_name: string
  branch: string
  clone_path: string | null
  git_url: string | null
  has_pat_token: boolean
  has_oauth_token: boolean
}

export type OAuthStartResponse = {
  authorize_url: string
  install_url: string
  state: string
  owner_name: string
  repo_name: string
  owner_pre_selected: boolean
  repo_pre_selected: boolean
}

export type OAuthStatusResponse = {
  complete: boolean
  oauth_token: string | null
  error: string | null
}

export async function testAccess(
  git_url: string,
  pat_token: string | null = null,
  auth_mode: string = "system_keys",
  oauth_token: string | null = null,
): Promise<TestAccessResponse> {
  return post("/api/git_sync/test_access", {
    git_url,
    pat_token,
    auth_mode,
    oauth_token,
  })
}

export async function listBranches(
  git_url: string,
  pat_token: string | null = null,
  auth_mode: string = "system_keys",
  oauth_token: string | null = null,
): Promise<ListBranchesResponse> {
  return post("/api/git_sync/list_branches", {
    git_url,
    pat_token,
    auth_mode,
    oauth_token,
  })
}

export async function cloneRepo(
  git_url: string,
  branch: string,
  pat_token: string | null = null,
  auth_mode: string = "system_keys",
  oauth_token: string | null = null,
): Promise<CloneResponse> {
  return post("/api/git_sync/clone", {
    git_url,
    branch,
    pat_token,
    auth_mode,
    oauth_token,
  })
}

export async function renameClone(
  clone_path: string,
  project_name: string,
  project_id: string,
): Promise<RenameCloneResponse> {
  return post("/api/git_sync/rename_clone", {
    clone_path,
    project_name,
    project_id,
  })
}

export async function testWriteAccess(
  clone_path: string,
  pat_token: string | null = null,
  auth_mode: string = "system_keys",
  oauth_token: string | null = null,
): Promise<TestAccessResponse> {
  return post("/api/git_sync/test_write_access", {
    clone_path,
    pat_token,
    auth_mode,
    oauth_token,
  })
}

export async function scanProjects(
  clone_path: string,
): Promise<ScanProjectsResponse> {
  return post("/api/git_sync/scan_projects", { clone_path })
}

export async function saveConfig(config: {
  project_id: string
  project_path: string
  git_url: string
  clone_path: string
  branch: string
  remote_name?: string
  pat_token?: string | null
  oauth_token?: string | null
  auth_mode?: string
  sync_mode?: string
}): Promise<GitSyncConfigResponse> {
  return post("/api/git_sync/save_config", config)
}

export async function getConfig(
  project_id: string,
): Promise<GitSyncConfigResponse | null> {
  const resp = await fetch(`${base_url}/api/git_sync/config/${project_id}`)
  if (resp.status === 404) {
    return null
  }
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function updateConfig(
  project_id: string,
  updates: {
    sync_mode?: string
    pat_token?: string
    oauth_token?: string
    auth_mode?: string
  },
): Promise<GitSyncConfigResponse> {
  return patch(`/api/git_sync/update_config/${project_id}`, updates)
}

export async function deleteConfig(
  project_id: string,
): Promise<{ message: string }> {
  const resp = await fetch(`${base_url}/api/git_sync/config/${project_id}`, {
    method: "DELETE",
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export async function oauthStart(git_url: string): Promise<OAuthStartResponse> {
  return post("/api/git_sync/oauth/start", { git_url })
}

export async function oauthStatus(state: string): Promise<OAuthStatusResponse> {
  const resp = await fetch(`${base_url}/api/git_sync/oauth/status/${state}`)
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(
      detail?.detail ||
        detail?.message ||
        `Failed to check OAuth status (${resp.status})`,
    )
  }
  return resp.json()
}

export function isGitHubUrl(url: string): boolean {
  return url.includes("github.com")
}

export function isGitLabUrl(url: string): boolean {
  const hostname = gitHostname(url)
  if (!hostname) return false
  return hostname === "gitlab.com" || hostname.startsWith("gitlab.")
}

export function gitHostname(url: string): string | null {
  try {
    // Handle SSH-style URLs like git@gitlab.example.com:org/repo.git
    const sshMatch = url.match(/^[\w-]+@([\w.-]+):/)
    if (sshMatch) return sshMatch[1]
    // Handle HTTPS-style URLs
    return new URL(url).hostname
  } catch {
    return null
  }
}

export function gitOwnerFromUrl(url: string): string | null {
  try {
    // Handle SSH-style URLs like git@github.com:Kiln-AI/repo.git
    const sshMatch = url.match(/^[\w-]+@[\w.-]+:([\w.-]+)\//)
    if (sshMatch) return sshMatch[1]
    // Handle HTTPS-style URLs
    const pathname = new URL(url).pathname
    const segments = pathname.split("/").filter(Boolean)
    return segments.length >= 1 ? segments[0] : null
  } catch {
    return null
  }
}

export function gitHubPatDeepLink(): string {
  return "https://github.com/settings/personal-access-tokens/new?name=Kiln+AI&description=Kiln+AI+auto+sync&contents=write&metadata=read&expires_in=none"
}

export function gitLabPatDeepLink(git_url: string): string {
  const host = gitHostname(git_url) || "gitlab.com"
  return `https://${host}/-/user_settings/personal_access_tokens?name=Kiln+AI&scopes=write_repository&description=Kiln+AI+auto+sync`
}

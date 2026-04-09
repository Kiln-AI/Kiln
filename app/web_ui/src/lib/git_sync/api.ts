import { base_url } from "$lib/api_client"

async function post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${base_url}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed: ${resp.statusText}`)
  }
  return resp.json()
}

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${base_url}${path}`)
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed: ${resp.statusText}`)
  }
  return resp.json()
}

export type TestAccessResponse = {
  success: boolean
  message: string
  auth_required: boolean
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

export type GitSyncConfigResponse = {
  sync_mode: string
  remote_name: string
  branch: string
  clone_path: string | null
  git_url: string | null
  has_pat_token: boolean
}

export async function testAccess(
  git_url: string,
  pat_token: string | null = null,
): Promise<TestAccessResponse> {
  return post("/api/git_sync/test_access", { git_url, pat_token })
}

export async function listBranches(
  git_url: string,
  pat_token: string | null = null,
): Promise<ListBranchesResponse> {
  return post("/api/git_sync/list_branches", { git_url, pat_token })
}

export async function cloneRepo(
  git_url: string,
  branch: string,
  pat_token: string | null = null,
  project_name: string = "project",
  project_id: string = "",
): Promise<CloneResponse> {
  return post("/api/git_sync/clone", {
    git_url,
    branch,
    pat_token,
    project_name,
    project_id,
  })
}

export async function testWriteAccess(
  clone_path: string,
  pat_token: string | null = null,
): Promise<TestAccessResponse> {
  return post("/api/git_sync/test_write_access", { clone_path, pat_token })
}

export async function scanProjects(
  clone_path: string,
): Promise<ScanProjectsResponse> {
  return post("/api/git_sync/scan_projects", { clone_path })
}

export async function saveConfig(config: {
  project_id: string
  git_url: string
  clone_path: string
  branch: string
  remote_name?: string
  pat_token?: string | null
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
  },
): Promise<GitSyncConfigResponse> {
  return post(`/api/git_sync/update_config/${project_id}`, updates)
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

export function isGitHubUrl(url: string): boolean {
  return url.includes("github.com")
}

export function gitHubPatDeepLink(): string {
  return "https://github.com/settings/personal-access-tokens/new?name=Kiln+AI&description=Kiln+AI+auto+sync&contents=write&metadata=read&expires_in=none"
}

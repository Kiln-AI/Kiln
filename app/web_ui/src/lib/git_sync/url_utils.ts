// Convert SSH-style git URLs to HTTPS equivalents
// e.g. git@github.com:user/repo.git -> https://github.com/user/repo.git
export function try_convert_ssh_to_https(url: string): string {
  const trimmed = url.trim()

  // git@host:user/repo.git -> https://host/user/repo.git
  const scp_match = trimmed.match(/^git@([\w.-]+):([\w./-]+)$/)
  if (scp_match) {
    return `https://${scp_match[1]}/${scp_match[2]}`
  }

  // ssh://git@host/user/repo.git -> https://host/user/repo.git
  const ssh_match = trimmed.match(/^ssh:\/\/git@([\w.-]+)\/([\w./-]+)$/)
  if (ssh_match) {
    return `https://${ssh_match[1]}/${ssh_match[2]}`
  }

  return trimmed
}

export function build_url_with_query_param(
  base_href: string,
  param_name: string,
  value: string | null,
): string {
  const url = new URL(base_href)
  if (value) {
    url.searchParams.set(param_name, value)
  } else {
    url.searchParams.delete(param_name)
  }
  return url.toString()
}

export function sync_url_query_param(
  param_name: string,
  value: string | null,
): void {
  const updated = build_url_with_query_param(
    window.location.href,
    param_name,
    value,
  )
  history.replaceState(null, "", updated)
}

export function read_url_query_param(param_name: string): string | null {
  const params = new URLSearchParams(window.location.search)
  return params.get(param_name)
}

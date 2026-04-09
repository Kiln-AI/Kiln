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

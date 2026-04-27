---
status: complete
---

# GitHub OAuth for Git Sync

The git import flow currently requires users to manually generate a Personal Access Token (PAT) on GitHub, which involves navigating to GitHub's token settings page. This page is buggy (URL parameters get dropped: https://github.com/orgs/community/discussions/188111), making the experience frustrating.

Add GitHub OAuth as the primary authentication method in `step_credentials.svelte` when the repo URL is a GitHub URL. OAuth lets users authenticate with a single click — they authorize the Kiln GitHub App and get redirected back with a token, no manual copy/paste needed.

PAT remains available as a fallback via a subtle "or use Personal Access Token" toggle link. For non-GitHub providers (GitLab, etc.), the existing PAT flow is unchanged.

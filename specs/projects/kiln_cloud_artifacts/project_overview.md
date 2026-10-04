---
status: draft
---

# Kiln Cloud on Cloudflare Artifacts

Entry for Cloudflare's "Build the next Git platform" competition (submissions close October 14, 2026). Goal: first place ($25K credits and the VIP speaker dinner). Most of it feels about 90% built already.

## Pitch

A mix of humans and agents working on the same Kiln project over git. Humans write evals and review results. Agents (Kiln's auto-research agent) do the research. Everyone works on one shared project, and git is the database between them.

It repeats the "git-backed SaaS" pitch (https://kiln.tech/blog/git_backed_saas), which is about 70% of the pitch already, plus "on Cloudflare Artifacts".

## Kiln Cloud

Right now Kiln is "bring your own cloud". With Artifacts, a "new project" button could create a shared, cloud-backed project with instant sync between users.

- Easy mode: bring your own Cloudflare account, or a small web app that creates the Artifacts repo and calls back to Kiln with credentials.
- Full mode: Kiln hosts it and owns the Artifacts namespace.

## References

- https://blog.cloudflare.com/artifacts-git-for-agents-beta/
- https://blog.cloudflare.com/next-git-platform-on-cloudflare/
- https://kiln.tech/blog/git_backed_saas
- Competition: https://www.cloudflare.com/git-competition (rules: https://www.cloudflare.com/documents/build-next-gen-git-platform-competition-terms.pdf)

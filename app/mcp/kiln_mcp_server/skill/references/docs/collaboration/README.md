---
description: How to collaborate with your team using Kiln
icon: people-arrows
online_url: https://docs.kiln.tech/docs/collaboration
---

# Collaboration

### Designed for Techies and Non-techies Alike

It's easy to collaborate with Kiln across teams with technical team members (devs, data-scientists), and non-technical team members (subject-matter experts, QA, labelers, etc).

We suggest [Git](references/docs/collaboration/#option-1-use-git) for technical teams, [shared drives](references/docs/collaboration/#option-2-use-shared-drives-for-non-technical-team-members) for non-technical teams, or a [mix](references/docs/collaboration/#option-3-combining-git-and-shared-drives) for mixed teams.

### **Recommended: Use Git!**

Kiln projects are simply a folder of files, making it easy to share them using Git. Add your project folder(s) to a git repo and you're set up with an excellent collaboration workflow with branches, pull requests, version control, access control, and more!

Kiln's [**Automatic Git Sync**](references/docs/collaboration/automatic-git-sync.md) feature makes it easy for non-technical team members to collaborate, even if they have no idea what git is. It's the best way to share Kiln projects with less technical team members like subject matter experts, QA, or PMs.

See [below](references/docs/collaboration/#collaboration-design) for how our file format is optimized for Git-based workflows.

### Option 2: Use Shared Drives

You can also host a Kiln project on a shared drive of your choice (Google Drive, Dropbox, iCloud, etc).

Be sure to review our [**Automatic Git Sync**](references/docs/collaboration/automatic-git-sync.md) feature before choosing a shared drive. It's more powerful, easier to setup, and harder to break than a shared drive.

Kiln project files will track who created them (internally in their JSON), which adds version history when many folks are making changes on the same shared drive. It's not as robust as Git history, but there is attribution built in.

### Collaboration Design

As you may have already guessed, you don't need to allow a third party to access your data, or maintain a database. Everything runs locally on your machine, and syncs through existing tools you control.

Kiln's data structure was designed with collaboration in mind:

* A Kiln project is simply a folder of files, which makes it compatible with a range of existing collaboration tools, from Git to Dropbox
* New items use unique random IDs to avoid conflicts/collisions, allowing many people to work concurrently on the same project.
* Project files are kept small and predominantly append-only. It's rare multiple people will need to work on the same file at the same time, reducing conflicts.
* The Kiln project files are JSON files, and are formatted to be easily used with diff tools and standard PR tools (GitHub, GitLab, etc).
* Static paths: even when changing the name of resource, the path will remain static.

### Kiln is an App: Don't Deploy Kiln as a Service

{% hint style="info" %}
This section is for engineers/developers attempting custom deployments. If you're a normal app user who launches Kiln as an app, just skip this!
{% endhint %}

Kiln is a desktop app, designed as an app. Even though internally it uses web tech (HTML), it's still an app designed to be run locally on each user's machine, not a hosted service.

We don't recommend or support trying to host it as a service and access it over the network. There are several major downsides/risks if you do.

<details>

<summary>Technical Details</summary>

There are several downsides/risks if you try to run as service:

* Security: there's no web-based logins or access controls, so anyone who can access the service can edit data and send requests. That's okay when running as an app locally behind your machine login, but brings risk when opening the service up to anyone over a network.
* Collaboration: If multiple users are sharing an instance of Kiln, all the created\_by tags in your dataset will all have the machine name of your VM/host, not the individuals.
* Data backup and history: if you run as suggested above, Git and/or the shared drive will provide data sync, backup and history. If you run on a single server, there's a higher risk of data loss if that server drive is lost/damaged.
* Native system Integrations: Kiln accesses OS features like the taskbar, local filesystem and custom folder-picker UI; these aren't available to web apps. We continue to add more native integrations over time.

The solution is just to have each user run Kiln locally on their own machine and collaborate using the two mechanisms above. It's quite easy and there are no compromises:

* We support all major platforms: Mac, Windows and Linux. Each has a user-friendly [installer](https://kiln.tech/download).
* You don't need to co-locate Kiln and your LLM/GPU servers. You can still connect Kiln to LLM services on another machine by setting a custom URL. See [AI Provider Setup](references/docs/models-and-ai-providers.md) for details.
* Kiln doesn't require a GPU and uses minimal system resources (CPU, memory).
* Kiln can work offline, and instantly. No network lag.

</details>

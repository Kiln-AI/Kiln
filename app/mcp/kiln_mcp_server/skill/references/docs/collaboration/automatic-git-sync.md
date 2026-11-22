---
description: Git, even if you've never used a terminal
icon: github
---

# Automatic Git Sync

<figure><img src="../../.gitbook/assets/git_collab.png" alt=""><figcaption></figcaption></figure>

{% hint style="info" %}
**Automatic Git Sync is in Beta**&#x20;
{% endhint %}

Historically, there have been two methods of collaboration for data teams: Git or cloud services. Both had tradeoffs.&#x20;

**Kiln adds a new option: automatic Git sync — providing the best of both worlds for data teams.**&#x20;

|                                    | Git                                                                        | Cloud Service                        | Kiln Automatic Git                                    |
| ---------------------------------- | -------------------------------------------------------------------------- | ------------------------------------ | ----------------------------------------------------- |
| **Ease of Use**                    | ❌ Requires terminal commands, dev tools, manual sync, conflict resolution  | :white\_check\_mark: Log in and go   | :white\_check\_mark: Connect and go                   |
| **History / Traceability**         | :white\_check\_mark: Detailed, traceable, revertible                       | ❌ Limited                            | :white\_check\_mark: Detailed, traceable, revertible  |
| **Data Portability**               | :white\_check\_mark: Easy portability on open formats                      | ❌ Custom formats, low portability    | :white\_check\_mark: Easy portability on open formats |
| **Privacy / Enterprise Approvals** | :white\_check\_mark: Existing Git host in 99% of orgs                      | ❌ Requires custom approvals          | :white\_check\_mark: Existing Git host in 99% of orgs |

### How it Works

Kiln allows you to choose how you work:

* **PMs / Subject Matter Experts / Designers:** connect an existing Kiln project in a repository in seconds via Kiln's UI. Any work you do (ratings, evals, data annotation) is automatically and instantly synced to Git, without any manual intervention. They never see a terminal, or have to learn Git.
* **Developers**: use manual Git tools, or automatically sync, or a mix. It's up to you!

#### Step 1: Set up your project repository

This is the only step requiring a developer or someone familiar with Git. All other users can use Kiln via the UI, with no knowledge of Git!

To set up your project:

* Create a Kiln project using the Kiln UI (or choose an existing project)
* Create an empty remote repository on GitHub, or the provider of your choice
* Push the new project to your remote repository. Follow your provider's instructions, but typically something like `git init -b main && git add . && git commit -m "initial commit" && git remote add origin <your-repo-url> && git push -u origin main`
* Ensure your team has read/write access to the repository using the provider's user management

{% hint style="info" %}
**Picking a Git Host**

Kiln works with any remote Git host. Most orgs already have a preferred provider, but there are small differences between how they work with Kiln.&#x20;

* **GitHub**: Just a few clicks to install via OAuth. It's easiest if the dev who initially sets up the project also installs and authorizes the app once, which will skip the "install app" step for all future users.
* **GitLab**: one-click link to generate a personal access token. Easy even for non-technical users. May require approvals based on organization policies.
* **Others**: supported via "personal access tokens". You'll need to provide your less technical users instructions for how to get a token for your chosen host.

Once connected: all hosts behave the same. The differences are only during setup.
{% endhint %}

#### Step 2: Share a "Connect" link with your Team

* Navigate to **Settings > Manage Projects > Import Project > Automatic Git Sync** in the Kiln UI
* Paste the https URL of your repo. For example `https://github.com/Kiln-AI/sync_test`  or  `https://github.com/Kiln-AI/sync_test.git` &#x20;
* Copy the URL from the browser — this is now a deep link to add this project on any team member's machine.
* Share the link with your team! If you're using a provider other than GitHub or GitLab, also share instructions on how to generate a personal access token.

#### Step 3: Connect the Repository&#x20;

New users can simply:

* Open the connect link generated above
* Follow the in-app steps to connect the project
* Use it like any other project, except know it's automatically kept up to date with your team!

{% hint style="info" %}
This path can be used for any user, regardless of technical background. The cloning, syncing, authorization, and all other details are managed automatically.
{% endhint %}

### What about Conflicts / Rebasing / etc?

**Short answer:** if you're using Kiln's automatic sync you don't need to worry about it.

Kiln has a powerful sync engine under the hood.&#x20;

* Each project is cloned to its own private and hidden repo to avoid conflicts
* The Kiln data model was already designed for Git: small immutable files, typically append only. The chance of conflicts is kept extremely low.
* We keep your local repo up to date with your remote repository (within 15 seconds). There's almost no time for drift or conflicts.
* If conflicts do occur (rare for above reasons), Kiln is self healing. It immediately detects the issue, rolls back and stashes any changes (zero data loss), and gets back into sync with remote. The UI shows a clear error; you can just hit "Submit" again and your change should now go through.

### Repository Structure

You can put the Kiln project in any folder of your repository. We'll scan for `project.kiln` files on first sync, and let you select which project to use if multiple exist.&#x20;

This also means you can put many Kiln projects into a single repository (don't worry, they won't cause conflicts).

### SSH Access

Kiln will work with SSH access URLs if your machine already has SSH set up with your Git provider. Just paste the SSH URL starting with `git@` when setting up the repository.

However, non-devs are very unlikely to have SSH set up. If SSH fails, we'll suggest trying the https URL and OAuth/token-based authentication instead.&#x20;

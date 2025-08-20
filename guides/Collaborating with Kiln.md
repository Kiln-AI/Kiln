# Guide: Collaborating with Kiln

---

# This guide as moved to [our docs](https://docs.kiln.tech/docs/collaboration). This page may be out of date.

We suggest reading the [latest version](https://docs.kiln.tech/docs/collaboration).

---

## Original Content

Kiln is designed to be a collaborative environment for building AI projects. This guide will help you understand how a team can collaborate with Kiln.

## Table of Contents

- [Sharing a Kiln Project](#sharing-a-kiln-project)
  - [Use Git](#use-git)
  - [Use Shared Drives for Non-Technical Team Members](#use-shared-drives-for-non-technical-team-members)
- [Using Tags to Organize Your Dataset](#using-tags-to-organize-your-dataset)

## Sharing a Kiln Project

It's quite easy for teams to collaborate on a Kiln project.

### Use Git

For most teams, it's really that simple. Share your Kiln project folder with a git repo and you're set up with an excellent collaboration workflow with branches, pull requests, version control, access control, and more.

This works because the Kiln project data structure was designed with git in mind:

- A Kiln project is really just a folder of files.
- New items use unique random IDs to avoid conflicts/collisions, allowing many people to work concurrently on the same project.
- Projects files are kept small - it's rare multiple people will need to work on the same file at the same time, reducing conflicts.
- The Kiln project files are JSON files, but always formatted to be easily used with diff tools and standard PR tools (GitHub, GitLab, etc).

### Use Shared Drives for Non-Technical Team Members

Not everyone is familiar with git, and that's okay! Since Kiln projects are just a folder of files, you can share the folder with your team using a shared drive of your choice (Google Drive, Dropbox, iCloud, etc).

You can combine this approach with git for version control on the project: simply host a branch on the shared drive. A technical team member can merge changes from the shared drive into main on occasion. The rest of the team can keep the benefits of git.

Kiln project files will track who created them internally, which can help when many folks are sharing the same drive. It's not as rich as git for tracking changes, but it's the easiest way to get started.

## Using Tags to Organize Your Dataset

Kiln uses tags to organize your dataset. You can add tags to any run/sample, and then filter by tag. This is a great way to organize your dataset and find specific runs.

Some examples of how you might use tags within a team:

- Working with eval teams:
  - Add the "needs_review" tag when data is ready for review by a human eval team
  - Ask a human eval team to review the new batch of synthetic data. New synth data is automatically tagged with "synthetic" and "synthetic_session_id".
- Defining a "golden" dataset: Have QA tag a "golden" data reserved for evals
- Bug resolution: QA can tag examples of a common issue with a tag (e.g. "issue_unprofessional_tone"). Data scientists can run evals of different methods of fixing the issue.
- Regression Testing: tag important customer use cases with a tag ("customer_use_case") and run evals to ensure the model doesn't regress on them prior to a new release.
- Fine-tuning: exclude tags from fine-tuning datasets (golden, customer_use_case, etc), to prevent contamination.

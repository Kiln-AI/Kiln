---
description: Kiln Issues are an AI-native issue tracker for AI teams
icon: bug
---

# Issues

<figure><img src="../.gitbook/assets/issuesbg-2.png" alt=""><figcaption></figcaption></figure>

Software teams have tools like Github Issues and JIRA for tracking issues. What should AI product teams use?

Kiln Issues are an AI-native issue tracker for AI teams. It doesn’t just collect bug reports, but keeps the structured data needed to reproduce, evaluate and fix AI system issues.

{% hint style="info" %}
**Under Development**: Kiln Issues are a new feature. Expect lots of improvements over the coming months!
{% endhint %}

### How are Kiln Issues Different than Github Issues, JIRA, etc?

Kiln issues are a way for teams to track known problems, just like Github Issues, JIRA, and countless other bug trackers.

Here's what makes Kiln Issues different from standard software bug trackers:

* **AI-Data Native**: Kiln Issues include the input/output data, model, provider, hyperparameters, and other data you need to diagnose and reproduce an issue
* **Evals Integration**: Issues include an eval that can measure if the issue is fixed or not
* **Synthetic Data Integration:** Kiln Issues can use data samples to generate synthetic data to reproduce the issue
* **Prompts:** Issues include prompts, not just freeform text discussions.
* **Longer lived:** Software bugs are usually closed once fixed. AI issues keep measuring over time, watching for regressions.

### Creating An Issue

To create an issue, select the Issue template when creating an Eval on the Eval tab. Include the following data:

* Prompt: A prompt describing the issue, which a judge model can use to determine if a model input/output pair exhibits the issue.
* Failure example (optional but recommended): an example of what failure looks like. Be sure to include this if the issue is subtle, subjective, or difficult to understand without examples.
* Passing example (optional)

<figure><img src="../.gitbook/assets/Screenshot 2025-07-17 at 1.40.52 PM.png" alt="" width="375"><figcaption><p>Create Issue UI</p></figcaption></figure>

### Evaluating An Issue

Issues are evals in the Kiln UI, but they go beyond a basic eval. Issue Evals have custom synthetic data gen templates, understanding that we want to generate inputs that reproduce a specific issue. It will help you easily create data samples from a single description (and optional examples).

Once you're done setting up your Issue Eval, you can use it to:

* Ensuring the issue is fixed: use the Issue Eval to confirm your fix (prompt change, model change, fine-tune) actually resolves the issue
* Ensuring the issue never regresses: keep running prior issue evals to ensure you don't accidentally regress the issue

Here's an example of the eval compare screen, ensuring several issues don't regress or are improved as they iterate/improve the AI system:

<figure><img src="../.gitbook/assets/Screenshot 2025-07-17 at 1.39.06 PM.png" alt="" width="375"><figcaption><p>Comparing several issues at one time</p></figcaption></figure>

### Philosophy: AI Product Evals work Best with Many Small Issue Evals <a href="#setup-team-evals" id="setup-team-evals"></a>

At Kiln we believe if creating an eval takes less than 10 minutes, your team will create them when they spot issues or fix bugs.

When evals become a habit instead of a chore, your AI system becomes dramatically more robust and your team moves faster.

Read our ~~manifesto~~ [guide on how to setup evals for your team](https://kiln.tech/blog/you_need_many_small_evals_for_ai_products#setup-team-evals). It covers:

* Many Small Evals Beat One Big Eval, Every Time
* The Benefits of Many Small Evals
* Evals vs Unit Testing
* 3 Steps to Set Up Your Team for Evals and Iteration

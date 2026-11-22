---
description: Ratings help multi-shot prompting, fine-tuning, evals, and more
icon: star
---

# Reviewing and Rating

Kiln includes a rating interface for rating dataset entries. This can be used to score the quality of the generated data, or to evaluate the quality of a model.

<figure><img src="../.gitbook/assets/Screenshot 2025-01-05 at 12.12.38 PM (1).png" alt="" width="341"><figcaption><p>Rating UI in Kiln Desktop</p></figcaption></figure>

### When Rating Options Appear

You'll see rating options on your dataset items:

* The "Overall Rating" will option will always appear
* After creating an [Eval](references/docs/evals-and-specs/evaluations.md), rating options will be visible for each sample in its golden dataset.

Not every rating will appear on every data sample, and that's okay! They only appear when they are useful, such as aligning a LLM-as-judge to human preference with a golden dataset. If a specific rating doesn't appear, it means it wouldn't be used and isn't necessary to rate this item by that criteria.&#x20;

Want to rate an item that isn't showing a rating field? Add a [tag](references/docs/organizing-datasets.md#using-tags-to-organize-your-dataset) like "eval\_NAME\_golden" which tells the system how that rating should be used. Once tagged, the necessary ratings will appear.

{% hint style="info" %}
### Legacy Task Requirements

Older version of Kiln had the concept of "task requirements": a rating criteria for all dataset samples. We've removed these going forward. Rating every single data sample by a criteria isn't necessary or helpful. As described above we now show the right ratings on the right items, and nothing more.
{% endhint %}

### Rating Option Parameters

Each rating option has a number of parameters:

* Name: the name of the requirement, which will appear in the rating UI. Limited in length to fit in the UI, but you can add more content in the instructions field below.
* Instructions: more details about the requirement. These will be available to reviewers in the UI (under the ![](<../.gitbook/assets/Screenshot 2025-01-05 at 12.18.52 PM (1).png>) icon).
* Rating Type: one of 5-star, pass/fail, pass/fail/critical.
* Priority: how important this criteria is to the task.

### Rating Types:

* **5-star**: a 1-5 star rating.
* **Pass/Fail**: A binary pass/fail rating.
* **Pass/Fail/Critical**: A ternary pass/fail/critical rating. It can be useful to add the "critical" level when there are criteria where some failures are exceptionally important to avoid. For example, a customer service bot could have a "tone" criteria, where casual/slang language would be a failure, but profanity or insulting the user would be critical.
* **Custom**: you can define a custom rating scale when using python library. However, you won't be able to use custom ratings in the Kiln UI.

### How Ratings are Used

Kiln uses ratings in a variety of ways:

* In evals, ratings of your golden dataset are used to benchmark and compare judges for evaluating your task. This helps you find the [ideal judge](references/docs/evals-and-specs/evaluations.md#finding-the-ideal-judge).
* Kiln's [automatic prompt generators](references/docs/prompts.md#prompt-generators) may incorporate highly rated samples into a prompt as a few-shot example. These filters to examples 4+ stars, and prefers 5-star ratings if available.
* When creating a [fine-tuning dataset](references/docs/fine-tuning/fine-tuning-guide.md), you may optionally filter the training data to highly rated content.
* When using the [python library](https://docs.kiln.tech/developers/python-library-quickstart), you can access or set ratings.

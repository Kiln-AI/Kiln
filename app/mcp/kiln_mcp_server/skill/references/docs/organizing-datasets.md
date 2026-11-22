---
description: Tag, Filter, Sort, Import, Freeze and Split
icon: tag
---

# Organizing Datasets

<figure><img src="../.gitbook/assets/dataset-2 (1).png" alt=""><figcaption></figcaption></figure>

### Using Tags to Organize Your Dataset

Kiln uses tags to organize your dataset. You can add tags to any run/sample, and then filter by tag. This is a great way to organize your dataset and find specific runs.

Some examples of how you might use tags within a team:

* Working with eval teams:
  * Add the "needs\_review" tag when data is ready for review by a human eval team
  * Ask a human eval team to review the new batch of synthetic data. New synth data is automatically tagged with "synthetic" and "synthetic\_session\_id".
* Defining a "golden" dataset: Have QA tag a "golden" data reserved for evals
* Bug resolution: QA can tag examples of a common issue with a tag (e.g. "issue\_unprofessional\_tone"). Data scientists can run evals of different methods of fixing the issue.
* Regression Testing: tag important customer use cases with a tag ("customer\_use\_case") and run evals to ensure the model doesn't regress on them prior to a new release.
* Fine-tuning: exclude tags from fine-tuning datasets (golden, customer\_use\_case, etc), to prevent contamination.

### Sort and Filter

The dataset view offers a number of tools that make working with large datasets easier:

* Filter: Tap the filter button (![](<../.gitbook/assets/filter 2.png>)) to filter to specific tags
* Sort: You can sort by any column by clicking its header
* Multi-select: you can enter "selection" mode by clicking the select button
  * Select any row by clicking it
  * Select a range of rows by clicking the first, then holding shift while clicking the last

### Batch Editing

Once you have selected rows you can perform a number of batch actions:

* Add tags
* Remove tags
* Delete dataset items

### Importing Data into your Dataset

If you already have a dataset, it's easy to import it into Kiln. Open the dataset tab, then click "Upload File" to add your data.

The format must be a CSV file with a header row. The following columns are supported:

* `input` \[Required] - The input to the task. If the task has an input schema, this must be a JSON string conforming to that schema.
* `output` \[Required] - The output of the task. If the task has an output schema, this must be a JSON string conforming to that schema.
* `reasoning` \[Optional] - If you model is a reasoning model that output reasoning/thinking text before the output (for example, R1, QwQ, etc), you can provide that text here. This will be visible in the UI, and available for fine-tuning a reasoning model.
* `chain_of_thought` \[Optional] - If you model output chain-of-thought text before the output, you can provide that text here. This will be visible in the UI, and available for fine-tuning a thinking model.
* `tags` \[Optional] - comma separated string listing the tags you want to add to this row. For example: `tag1, tag2`.

<figure><img src="../.gitbook/assets/Screenshot 2025-03-15 at 12.59.27 PM.png" alt="" width="375"><figcaption><p>The CSV Import UI</p></figcaption></figure>

{% hint style="info" %}
If you prefer working in python, or have a complex import use case, our Python SDK can be used to add data to a Kiln project. It includes validators that ensures your data conforms to the needed schemas.

See our [python docs for an example](https://kiln-ai.github.io/Kiln/kiln_core_docs/kiln_ai.html#load-an-existing-dataset-into-a-kiln-task-dataset).
{% endhint %}

### Dataset Splits

When creating a fine-tune, you can define a "dataset split". This is a frozen subset of your data.

* Dataset splits may be broken into sub-sets like "train", "validation" and "test" which are useful for systematically training and evaluating models.
* Dataset splits will randomly assign items between sub-sets (train/test/val), but the assignment is static. Items do not shift between subsets once the dataset split is created.
* Dataset splits do not grow/change when you add new data. They are frozen at the point in time when they are created. This makes it easier to run multiple experiments (fine-tunes, evals, etc) on exactly the same training/eval datasets.

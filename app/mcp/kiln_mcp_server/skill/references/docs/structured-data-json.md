---
icon: brackets-curly
---

# Structured Data / JSON

<figure><img src="../.gitbook/assets/json.png" alt=""><figcaption></figcaption></figure>

Structured data is a first-class citizen in Kiln.

* JSON input/output is supported for any task.
* You can define input/output schemas for each task you create.
* We automatically detect when a AI model doesn't produce output in the correct format.
* No data will be saved into the dataset without first passing validation, which keeps the dataset clean.
* Our [included models](references/docs/models-and-ai-providers.md#included-models-recommended) are tested for JSON compatibility, and models that don't perform well with structured data will show a warning if you attempt to use them on tasks with structured output.

### Creating a Schema

Our easy-to-use visual schema builder lets you create and use structured schemas. Define your input and output schemas in our UI when creating a task.

{% hint style="info" %}
You can't edit the input/output schemas after creating a task, as that would invalidate all prior data. Create a new task with your updated schema instead.
{% endhint %}

<figure><img src="../.gitbook/assets/Screenshot 2025-01-08 at 12.38.31 PM.png" alt="" width="375"><figcaption><p>Kiln's Visual Schema Editor</p></figcaption></figure>

### Raw JSON Schema

For technical users, we support any valid [JSON-schema](https://json-schema.org) for inputs and output schemas.

JSON schema is more powerful than the visual editor, allowing arrays, nested objects, enums, constraints and more. You can use raw JSON schemas from the Python library, or from the UI (by picking an array type).

{% hint style="warning" %}
We only recommend JSON schema for technical users/developers. It's much more complex than the visual editor.

Errors in the schema will likely result in bugs when running your task.
{% endhint %}

### Troubleshooting Structured Data Issues

LLMs aren't always great at producing valid JSON output. Kiln does its best to use a variety of techniques to get the correct output, but it's never guaranteed.

You may see errors in the UI if the model produces invalid JSON, or JSON that doesn't match the output schema of your task.

Here are some tips to getting consistent JSON output:

* Use a model that is suggested for JSON output. The model drop down will warn you if you're using an untested model, or a model with known issues producing JSON.
* Consider [fine-tuning a model](references/docs/fine-tuning/fine-tuning-guide.md) on synthetic data from a larger and more reliable model. Fine tuning is a great way to get consistent format output, and you can get models as small as 1B parameters to consistently produce JSON with fine-tuning.
* Don't use an output schema unless necessary. If you only require plain text output from your task, be sure to select plaintext as the output format when creating the task. This will work with well with any model.
* Try adding an example of the output structure you want to your prompt. You can do this in `Settings > Edit Task > Task Instructions` or via a [custom prompt](references/docs/prompts.md#custom-prompts-saved-prompts). For example, add this to your prompt:

````
Provide the output in the following JSON format:
```
{
  "setup": "Why did the chicken cross the road",
  "punchline": "To get to the other side."
}
 ``` 
````

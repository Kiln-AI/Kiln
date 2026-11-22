---
description: Build fine-tuned models for calling a set of tools, like MCP
---

# Fine-Tuning for Tool Use

Kiln can fine-tune a model for calling a specific set of tools. The fine-tuned models can improve over the base model by:

* Learning when to call each tool, and when not to
* Learning when to choose one tool over another
* Learning how to format tool calls and tool call parameters. This greatly reduces error rates over the base model, making smaller and faster models viable.

Together, this means you can improve agent performance and lower costs.

#### Building a Fine-Tuning Training Dataset for Tool Calling

To create a fine-tune targeting tool calling, you must generate a training set specifically for tool calling.&#x20;

{% hint style="info" %}
The tool set available during training data generation must exactly match the tool set your fine-tune targets.

Kiln disallows training on samples that don't have a matching toolset. We don't want to train on these as the fine-tuned model would improperly learn not to call a tool, even when a tool call would have been appropriate.

This doesn’t mean every tool needs to be called in every training sample. Only that every tool was available to be called.
{% endhint %}

Kiln makes building a tool-calling training dataset easy:

1. Open the Fine-Tune tab.
2. Click “Create Fine Tune”.
3.  Select the set of tools that the model should learn to call.

    <figure><img src="../../.gitbook/assets/Screenshot 2026-01-08 at 8.07.16 PM (2).png" alt="" width="375"><figcaption><p>Selecting tools available to the fine-tuned model</p></figcaption></figure>


4.  Click “Add Fine-Tuning Data” to launch Kiln's synthetic data generation tool.

    <figure><img src="../../.gitbook/assets/image.png" alt="" width="375"><figcaption></figcaption></figure>


5. Generate synthetic training data using Kiln's [synthetic data gen](references/docs/synthetic-data-generation.md) tool. It will automatically select the correct tools for you when generating sample outputs.

#### Distilling Larger Models and Longer Prompts for Better Tool Calling

Beyond learning tool-call formatting, your fine-tuned model must learn _when_ to call each tool and _which parameters_ to pass. The quality of the resulting model depends heavily on the quality of the training dataset—so how do you build a high-quality dataset for tool calling?

The answer is typically [_distillation_](https://en.wikipedia.org/wiki/Knowledge_distillation): training a model on the outputs of another model. By using larger models with carefully designed prompts that specify how tools should be used, you can generate a high-quality dataset that demonstrates correct tool usage. You can then fine-tune a smaller, faster, and cheaper model to reproduce similar quality.

|                                                                                                                             | Training Set Generation                                                                                                           | Fine-Tuned Model                                                                        |
| --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Model                                                                                                                       | Large Model                                                                                                                       | Smaller Model                                                                           |
| Prompt                                                                                                                      | Long prompt detailing tool calling strategy. This includes when each tool should be used and which parameters to pass. | Short prompt focused on task. Does not need to address tool-calling strategy in detail. |
| Reasoning Mode                                                                                                              | Recommended to Enable                                                                                                             | Optional                                                                                |
| Cost per Token                                                                                                              | Expensive                                                                                                                         | Cheap                                                                                   |
| Speed                                                                                                                       | Slower                                                                                                                            | Faster                                                                                  |
| <p>Tool Usage Evals<br><a href="references/docs/fine-tuning/fine-tuning-for-tool-use.md#evaluating-tool-use"><em>Always measure to confirm</em></a></p> | High quality                                                                                                                      | High quality                                                                            |
| Origin of Tool Calling Logic                                                                                                | Base model + detailed strategy in prompt                                                                                          | Learned during fine-tuning                                                              |

#### Create a Tool Calling Fine-Tune

Once you’ve created a training set, return to the “Create a Fine Tune” screen to start training. Select a base model, the tools you want, and the dataset you’ve created to start training. See our [fine-tuning guide](references/docs/fine-tuning/fine-tuning-guide.md) for additional details.

<figure><img src="../../.gitbook/assets/Screenshot 2026-01-08 at 9.01.36 PM.png" alt="" width="375"><figcaption></figcaption></figure>

{% hint style="info" %}
You must select a base model that supports tool calling. Kiln will disable tool calling training if the selected base model was not trained for tool calling.
{% endhint %}

{% hint style="success" %}
Kiln will convert your training data into the base model's tool calling format automatically.
{% endhint %}

#### Running a Tool Calling Fine-Tune

When running a Tool Calling Fine-Tune in Kiln, we’ll automatically populate the same set of tools it was trained on.&#x20;

Adding or removing tools will show a warning, as this model is unlikely to perform well with tools that were not in its training dataset.&#x20;

{% hint style="info" %}
If deploying a fine-tune created in Kiln, always provide the same tools as it was trained to use.
{% endhint %}

#### Evaluating Tool Use

Kiln has a custom eval for [evaluating appropriate tool use](references/docs/evals-and-specs/evaluate-appropriate-tool-use.md). We suggest using it to compare the base model to your fine-tune, to confirm performance is improving.

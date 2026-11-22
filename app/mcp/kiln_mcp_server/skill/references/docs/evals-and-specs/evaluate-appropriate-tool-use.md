---
description: Test your model's ability to appropriately invoke tools
---

# Evaluate Appropriate Tool Use

<figure><img src="../../.gitbook/assets/tool_use.png" alt=""><figcaption></figcaption></figure>

{% hint style="success" %}
**It doesn't matter how well a tool works if it isn't invoked when needed.**&#x20;

Kiln can evaluate your agent's tool use to help find issues early.
{% endhint %}

### **Overview**

Appropriate Tool Use evals measure how well your model decides when to invoke a specific tool. It checks that:

* The tool is called when needed
* The tool isn’t called when it shouldn’t be
* The parameters passed to the tool are correct

This approach includes:

* Generating large eval datasets quickly using synthetic data generation
* Creating realistic scenarios that comprehensively test tool invocation behaviour
* Testing both appropriate use cases (when the tool should be called) and inappropriate cases (when it shouldn't)
* Systematically testing different task configurations to optimize tool calling performance

#### The Workflow

This guide covers the tool-specific aspects of appropriate tool use evals. For the general eval workflow including setting up judges, adding human ratings, finding the ideal judge, and finding the ideal run configuration, see [main guide to evaluations](references/docs/evals-and-specs/evaluations.md).

The key differences for appropriate tool use evals are:

* Creating the eval requires specifying tool use guidelines: which tool, when it should/shouldn't be called
* Synthetic data generation automatically enables the tool being evaluated
* Human ratings require checking the message trace to see tool invocation details
* Judge examines the entire message trace to determine appropriate tool use, not just final response
* Finding the ideal run configuration involves ensuring the tool being evaluated is available in the run configuration you are evaluating

#### Creating an Appropriate Tool Use Eval

From the "Eval" tab in Kiln's UI, create a new evaluator using the "Appropriate Tool Use" template.

{% hint style="info" %}
**Appropriate Tool Use**: This template is designed for evaluating tool calling behaviour and includes evaluation steps that examine the full conversation trace to determine if the model correctly decided to call (or not call) the selected tool with appropriate parameters.
{% endhint %}

When creating the eval, you'll need to specify the tool to evaluate and guidelines. This eval will test whether the model appropriately invokes this tool according to your guidelines.

**Appropriate Tool Use Guidelines**

Provide guidelines or examples of when the tool should be used. This is required and helps both the synthetic data generator create relevant test cases and the judge understand correct usage patterns.

**Web Research** tool examples:

* "Questions requiring current information, recent events, or up-to-date data that may have changed"
* "Questions about specific facts, statistics, or information that may not be in the model's training data"
* "Questions asking for comparisons, reviews, or analysis that benefit from multiple sources"

**Inappropriate Tool Use Guidelines (Optional)**

Optionally provide guidelines or examples of when the tool should NOT be used. This helps create a more comprehensive test dataset that includes clear negative cases.

**Web Research** tool examples:

* "General conversation, greetings, or questions that don't require factual information"
* "Questions about well-established facts, definitions, or concepts that are reliably in the model's training data"
* "Simple calculations, math problems, or questions that can be answered without external information"

Once configured, save your eval to proceed.

#### Generate Synthetic Test Data

After creating your eval, populate your eval dataset using synthetic data generation. Clicking "Add Eval Data" from the Evals UI, and selecting "Synthetic Data" will launch the synthetic data generation tool with the proper eval tags already populated.

{% hint style="info" %}
**Tool-Specific Behaviour**: When generating outputs in the synthetic data generation flow, **the tool you're evaluating is automatically enabled** for this step, ensuring your model has the opportunity to call it when appropriate. The system captures the full conversation trace, including whether the tool was called and what parameters were used.

See our [Synthetic Data Generation docs](references/docs/synthetic-data-generation.md) for more guidance.
{% endhint %}

### Add Human Ratings

When rating your golden dataset for appropriate tool use evals, you'll need to check both the dataset entry and the Message Trace to see if the tool was invoked and with what parameters.

1. Click the `Rate Golden Dataset` button on the eval screen to go to the dataset view filtered to your golden dataset. For general guidance on rating, see [Reviewing and Rating](references/docs/reviewing-and-rating.md).
2. **View the Message Trace** for each dataset entry to inspect:
   * Whether the tool was called
   * What parameters were passed to the tool

This allows you to accurately rate whether the tool was called appropriately based on the full conversation context.

For your eval output rating, you should click "Pass" if the model's behaviour was appropriate and "Fail" if not.

#### Pass = Appropriate Tool Use

* The model called the tool with correct parameters at the appropriate time
* The model correctly did not call the tool as it was not needed

#### Fail = Inappropriate Tool Use

* The model should have called the tool but did not
* The model called the tool but shouldn't have, or called it with wrong parameters.

For more details on the human rating workflow, see [Add Human Ratings](references/docs/evals-and-specs/evaluate-appropriate-tool-use.md#add-human-ratings).

#### Finding the Ideal Judge

Before evaluating different run configurations, you need to create a judge. The eval you created defines the goal, but the judge defines how it's run (judge algorithm, model, and instructions).

For detailed guidance on selecting judge algorithms (LLM as Judge vs G-Eval), models, and customizing evaluation steps, see [Add a Judge to your Eval](references/docs/evals-and-specs/evaluations.md#add-a-judge-to-your-eval).

The judge will examine the full conversation trace to determine appropriate tool use, using your provided guidelines.

For guidance on comparing judges and finding the one that best aligns with human preferences, see [Finding the Ideal Judge](references/docs/evals-and-specs/evaluations.md#finding-the-ideal-judge).

#### Finding the Ideal Run Configuration

Once you have a judge set up, you can evaluate different configurations for running your task. Since appropriate tool use evals specifically test your model's tool calling behaviour, you'll want to test configurations such as:

* Different task models (some models are better at tool calling than others)
* Different prompts and system instructions
* Different sets of available tools (testing with varying numbers of tools can help identify optimal tool configurations)

You will also be able to see the tools available to each run configuration. Keep in mind that any run configuration without access to the tool you are evaluating will produce unreliable scores, as the model cannot actually invoke the tool being tested.

<figure><img src="../../.gitbook/assets/Screenshot 2025-11-14 at 1.33.24 PM.png" alt="" width="375"><figcaption><p>Comparing Run Configurations</p></figcaption></figure>

For detailed guidance on selecting and comparing task model options, see [Finding the Ideal Run Method](references/docs/evals-and-specs/evaluations.md#finding-the-ideal-run-method).

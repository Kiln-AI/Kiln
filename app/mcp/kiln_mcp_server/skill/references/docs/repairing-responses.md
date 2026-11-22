---
description: '"Teach the model, you will" - ML Yoda'
icon: hammer
---

# Repairing Responses

<figure><img src="../.gitbook/assets/Repair.png" alt=""><figcaption></figcaption></figure>

Kiln offers a somewhat novel option in our "Run" UI and data model: repairs. Instead of simply evaluating/rating AI responses, we offer the ability to "repair" any responses which are reviewed less than 5-stars.

### Repair Process

The repair process is:

1. Rate the model response. If the overall rating is 5-star, you're done!
2. A human offers repair instructions, describing what was wrong, and how it can be improved, then click "Repair".
3. The model generates a new response, given the prompt, initial flawed response, and the human repair instructions.
4. A human evaluates the response, and either accepts it as 5-star (you're done!), or returns to step 2 to iterate on repair instructions until the model can produce a 5-star response.

### Why Repair Instead of Simply Correct the Response

Repairing generates some useful data in our dataset, such as:

* Examples of failures.
* Feedback on failures. Specifically, feedback we know the model can understand, because it has demonstrated it can generate a 5-star response after receiving it.
* More nuanced examples: the difference between a 4-star and 5-star response for the same input can be helpful for model evaluation and training.

### Where is this data used?

Currently this data is used in [repair prompts](references/docs/prompts.md#prompt-builders-prompt-styles): a prompt style that includes both all of the data above in a multi-shot prompt format.

In the future we plan to use it in other places, like evaluations, so collecting it now will help you in the future.

You can also use this data for your own evaluation processes via our [python library](https://docs.kiln.tech/developers/python-library-quickstart). For example, clustering repair feedback to identify recurring issues.

### Why can't I just manually correct errors?

This is planned! For now, please use the repair system for corrections.

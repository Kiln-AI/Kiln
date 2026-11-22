---
description: How to troubleshoot errors from the logs
icon: user-helmet-safety
---

# Troubleshooting & Logs

### First: Consider Model Errors

Most bug reports we get aren't actually bugs in Kiln, but models failing to perform the task asked of them. Please read the error messages carefully, and follow the suggestions.

* If the error is related to structured data, see [Troubleshooting Structured Data Issues](references/docs/structured-data-json.md#troubleshooting-structured-data-issues)
* Try another (smarter) model to see if the issue persists, of if it's isolated to a specific model.

### Second: Review the Error Message For Guidance

Often the error message explains how to resolve the issue. Some examples:

* Issues from connected services (no credit, rate-limits, etc) will need to be corrected with those services
* "Model not found, inaccessible, and/or not deployed" - A Fireworks API message that the model needs to be re-deployed. For fine-tunes, Kiln can re-deploy the model for you - just open the fine-tune in the "Fine Tune" tab.

### Third: Check The Logs

Kiln writes out error logs to the path \`\~/.kiln\_ai/logs/\*.log\`.

Check your latest log file for a stack trace of any errors, which can help understand the issue. If you think it's a bug in Kiln and not a model issue, please [file a bug](https://github.com/Kiln-AI/Kiln/issues), following the bug template and attaching logs.


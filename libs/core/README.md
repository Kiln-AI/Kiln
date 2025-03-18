# Kiln AI Core Library

<p align="center">
    <picture>
        <img width="205" alt="Kiln AI Logo" src="https://github.com/user-attachments/assets/5fbcbdf7-1feb-45c9-bd73-99a46dd0a47f">
    </picture>
</p>

[![PyPI - Version](https://img.shields.io/pypi/v/kiln-ai.svg?logo=pypi&label=PyPI&logoColor=gold)](https://pypi.org/project/kiln-ai)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/kiln-ai.svg)](https://pypi.org/project/kiln-ai)
[![Docs](https://img.shields.io/badge/docs-pdoc-blue)](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html)

---

## Installation

```console
pip install kiln_ai
```

## About

This package is the Kiln AI core library. There is also a separate desktop application and server package. Learn more about Kiln AI at [getkiln.ai](https://getkiln.ai) and on Github: [github.com/Kiln-AI/kiln](https://github.com/Kiln-AI/kiln).

# Guide: Using the Kiln Python Library

In this guide we'll walk common examples of how to use the library.

## Documentation

The library has a [comprehensive set of docs](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html).

## Table of Contents

- [Using the Kiln Data Model](#using-the-kiln-data-model)
  - [Understanding the Kiln Data Model](#understanding-the-kiln-data-model)
  - [Datamodel Overview](#datamodel-overview)
  - [Load a Project](#load-a-project)
  - [Load an Existing Dataset into a Kiln Task Dataset](#load-an-existing-dataset-into-a-kiln-task-dataset)
  - [Using your Kiln Dataset in a Notebook or Project](#using-your-kiln-dataset-in-a-notebook-or-project)
  - [Using Kiln Dataset in Pandas](#using-kiln-dataset-in-pandas)
  - [Building and Running a Kiln Task from Code](#building-and-running-a-kiln-task-from-code)
  - [Adding Custom Model or AI Provider from Code](#adding-custom-model-or-ai-provider-from-code)
- [Full API Reference](#full-api-reference)

## Installation

```bash
pip install kiln-ai
```

## Using the Kiln Data Model

### Understanding the Kiln Data Model

Kiln projects are simply a directory of files (mostly JSON files with the extension `.kiln`) that describe your project, including tasks, runs, and other data.

This dataset design was chosen for several reasons:

- Git compatibility: Kiln project folders are easy to collaborate on in git. The filenames use unique IDs to avoid conflicts and allow many people to work in parallel. The files are small and easy to compare using standard diff tools.
- JSON allows you to easily load and manipulate the data using standard tools (pandas, polars, etc)

The Kiln Python library provides a set of Python classes that which help you easily interact with your Kiln dataset. Using the library to load and manipulate your dataset is the fastest way to get started, and will guarantees you don't insert any invalid data into your dataset. There's extensive validation when using the library, so we recommend using it to load and manipulate your dataset over direct JSON manipulation.

### Datamodel Overview

Here's a high level overview of the Kiln datamodel. A project folder will reflect this nested structure:

- Project: a Kiln Project that organizes related tasks
  - Task: a specific task including prompt instructions, input/output schemas, and requirements
    - TaskRun: a sample (run) of a task including input, output and human rating information
    - Finetune: configuration and status tracking for fine-tuning models on task data
    - Prompt: a prompt for this task
    - DatasetSplit: a frozen collection of task runs divided into train/test/validation splits

### Load a Project

Assuming you've created a project in the Kiln UI, you'll have a `project.kiln` file in your `~/Kiln Projects/Project Name` directory.

```python
from kiln_ai.datamodel import Project

project = Project.load_from_file("path/to/your/project.kiln")
print("Project: ", project.name, " - ", project.description)

# List all tasks in the project, and their dataset sizes
tasks = project.tasks()
for task in tasks:
    print("Task: ", task.name, " - ", task.description)
    print("Total dataset size:", len(task.runs()))
```

### Load an Existing Dataset into a Kiln Task Dataset

If you already have a dataset in a file, you can load it into a Kiln project.

**Important**: Kiln will validate the input and output schemas, and ensure that each datapoint in the dataset is valid for this task.

- Plaintext input/output: ensure "output_json_schema" and "input_json_schema" not set in your Task definition.
- JSON input/output: ensure "output_json_schema" and "input_json_schema" are valid JSON schemas in your Task definition. Every datapoint in the dataset must be valid JSON fitting the schema.

Here's a simple example of how to load a dataset into a Kiln task:

```python

import kiln_ai
import kiln_ai.datamodel

# Created a project and task via the UI and put its path here
task_path = "/Users/youruser/Kiln Projects/test project/tasks/632780983478 - Joke Generator/task.kiln"
task = kiln_ai.datamodel.Task.load_from_file(task_path)

# Add data to the task - loop over you dataset and run this for each item
item = kiln_ai.datamodel.TaskRun(
    parent=task,
    input='{"topic": "AI"}',
    output=kiln_ai.datamodel.TaskOutput(
        output='{"setup": "What is AI?", "punchline": "content_here"}',
    ),
)
item.save_to_file()
print("Saved item to file: ", item.path)
```

And here's a more complex example of how to load a dataset into a Kiln task. This example sets the source of the data (human in this case, but you can also set it be be synthetic), the created_by property, and a 5-star rating.

```python
import kiln_ai
import kiln_ai.datamodel

# Created a project and task via the UI and put its path here
task_path = "/Users/youruser/Kiln Projects/test project/tasks/632780983478 - Joke Generator/task.kiln"
task = kiln_ai.datamodel.Task.load_from_file(task_path)

# Add data to the task - loop over you dataset and run this for each item
item = kiln_ai.datamodel.TaskRun(
    parent=task,
    input='{"topic": "AI"}',
    input_source=kiln_ai.datamodel.DataSource(
        type=kiln_ai.datamodel.DataSourceType.human,
        properties={"created_by": "John Doe"},
    ),
    output=kiln_ai.datamodel.TaskOutput(
        output='{"setup": "What is AI?", "punchline": "content_here"}',
        source=kiln_ai.datamodel.DataSource(
            type=kiln_ai.datamodel.DataSourceType.human,
            properties={"created_by": "Jane Doe"},
        ),
        rating=kiln_ai.datamodel.TaskOutputRating(score=5,type="five_star"),
    ),
)
item.save_to_file()
print("Saved item to file: ", item.path)
```

### Using your Kiln Dataset in a Notebook or Project

You can use your Kiln dataset in a notebook or project by loading the dataset into a pandas dataframe.

```python
import kiln_ai
import kiln_ai.datamodel

# Created a project and task via the UI and put its path here
task_path = "/Users/youruser/Kiln Projects/test project/tasks/632780983478 - Joke Generator/task.kiln"
task = kiln_ai.datamodel.Task.load_from_file(task_path)

runs = task.runs()
for run in runs:
    print(f"Input: {run.input}")
    print(f"Output: {run.output.output}")

print(f"Total runs: {len(runs)}")
```

### Using Kiln Dataset in Pandas

You can also use your Kiln dataset in a pandas dataframe, or a similar script for other tools like polars.

```python
import glob
import json
import pandas as pd
from pathlib import Path

task_dir = "/Users/youruser/Kiln Projects/test project/tasks/632780983478 - Joke Generator"
dataitem_glob = task_dir + "/runs/*/task_run.kiln"

dfs = []
for file in glob.glob(dataitem_glob):
    js = json.loads(Path(file).read_text())

    df = pd.DataFrame([{
        "input": js["input"],
        "output": js["output"]["output"],
    }])

    # Alternatively: you can use pd.json_normalize(js) to get the full json structure
    # df = pd.json_normalize(js)
    dfs.append(df)
final_df = pd.concat(dfs, ignore_index=True)
print(final_df)
```

### Building and Running a Kiln Task from Code

```python
# Step 1: Create or Load a Task -- choose one of the following 1.A or 1.B

# Step 1.A: Optionally load an existing task from disk
# task = datamodel.Task.load_from_file("path/to/task.kiln")

# Step 1.B: Create a new task in code, without saving to disk.
task = datamodel.Task(
    name="test task",
    instruction="Tell a joke, given a subject.",
)
# replace with a valid JSON schema https://json-schema.org for your task (json string, not a python dict).
# Or delete this line to use plaintext output
task.output_json_schema = json_joke_schema

# Step 2: Create an Adapter to run the task, with a specific model and provider
adapter = adapter_for_task(task, model_name="llama_3_1_8b", provider="groq")

# Step 3: Invoke the Adapter to run the task
task_input = "cows"
response = await adapter.invoke(task_input)
print(f"Output: {response.output.output}")

# Step 4 (optional): Load the task from disk and print the results.
#  This will only work if the task was loaded from disk, or you called task.save_to_file() before invoking the adapter (ephemeral tasks don't save their result to disk)
task = datamodel.Task.load_from_file(tmp_path / "test_task.kiln")
for run in task.runs():
    print(f"Run: {run.id}")
    print(f"Input: {run.input}")
    print(f"Output: {run.output}")

```

### Adding Custom Model or AI Provider from Code

You can add additional AI models and providers to Kiln.

See our docs for more information, including how to add these from the UI:

- [Custom Models From Existing Providers](https://docs.getkiln.ai/docs/models-and-ai-providers#custom-models-from-existing-providers)
- [Custom OpenAI Compatible Servers](https://docs.getkiln.ai/docs/models-and-ai-providers#custom-openai-compatible-servers)

You can also add these from code. The kiln_ai.utils.Config class helps you manage the Kiln config file (stored at `~/.kiln_settings/config.yaml`):

```python
# Addding an OpenAI compatible provider
name = "CustomOllama"
base_url = "http://localhost:1234/api/v1"
api_key = "12345"
providers = Config.shared().openai_compatible_providers or []
existing_provider = next((p for p in providers if p["name"] == name), None)
if existing_provider:
    # skip since this already exists
    return
providers.append(
    {
        "name": name,
        "base_url": base_url,
        "api_key": api_key,
    }
)
Config.shared().openai_compatible_providers = providers
```

```python
# Add a custom model ID to an existing provider.
new_model = "openai::gpt-3.5-turbo"
custom_model_ids = Config.shared().custom_models
existing_model = next((m for m in custom_model_ids if m == new_model), None)
if existing_model:
    # skip since this already exists
    return
custom_model_ids.append(new_model)
Config.shared().custom_models = custom_model_ids
```

## Full API Reference

The library can do a lot more than the examples we've shown here.

See the full API reference in the [docs](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html) under the `Submodules` section of the sidebar.

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

This package is the Kiln AI core library. There is also a separate desktop application and server package. Learn more about Kiln AI at [getkiln.ai](https://getkiln.ai)

- Github: [github.com/Kiln-AI/kiln](https://github.com/Kiln-AI/kiln)
- Core Library Docs: [https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html](https://kiln-ai.github.io/Kiln/kiln_core_docs/index.html)

## Quick Start

```python
from kiln_ai.datamodel import Project

print("Reading Kiln project")
project = Project.load_from_file("path/to/project.kiln")
print("Project: ", project.name, " - ", project.description)

task = project.tasks()[0]
print("Task: ", task.name, " - ", task.description)
print("Total dataset size:", len(task.runs()))

# ... app specific code using the typed kiln datamodel

# Alternatively, load data into pandas or a similar tool:
import glob
import json
import pandas as pd
from pathlib import Path

dataitem_glob = str(task.path.parent) + "/runs/*/task_run.kiln"

dfs = []
for file in glob.glob(dataitem_glob):
    js = json.loads(Path(file).read_text())
    df = pd.json_normalize(js)
    dfs.append(df)
final_df = pd.concat(dfs, ignore_index=True)
print(final_df)
```

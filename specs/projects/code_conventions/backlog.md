# Backlog

- [ ] **B1 — `global-stmt` matches the word "global" at the start of a docstring line**
  The pattern `^\s*global\s+\w` hits prose such as a docstring line that starts with "global structlog or stdlib logging settings…". It was found while calibrating kiln_server's copy of the gate. A fix is either to require a Python identifier list after `global` and nothing else on the line, or to skip lines inside docstrings. Fix it in the Kiln gate; kiln_server keeps its own copy.

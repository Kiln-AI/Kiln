# Using Docker Sandboxes

## Create Your Sandbox

Build custom docker image

```bash
docker build -t kiln_opencode_template -f utils/docker_sandboxes/DockerfileOpencode utils/docker_sandboxes
```

Back at project root, create and setup sandbox:

```bash
# OLD docker sandbox run -t kiln_opencode_template opencode .
```

```bash
# Create Sandbox
docker sandbox create -t kiln_opencode_template opencode .
# npm i, but in /tmp where it won't overwrite
docker sandbox exec opencode-kiln_new bash -c "cp $PWD/app/web_ui/package*.json /tmp && cd /tmp && ls && npm i"
docker sandbox exec opencode-kiln_new bash -c "cd $PWD && uv sync"
```

Note: log into claude code or opencode in UI

To use bash:
```bash
docker sandbox exec -it opencode-kiln_new bash
```

Note: the project path in the container is the same as your local dev path

If you need it, delete your sandbox and start fresh:

```bash
docker sandbox rm opencode-kiln_new
```

## Pending / Improvements

- Docker can't handle parallel tests. Might need more memory? Detects and runs single threaded now
- `Seccomp` limits mean some things in checks.sh won't work. Detect and bypass for now. Hopefully docker fixes this, esbuild doesn't work, and that seems like their issue. https://github.com/docker/desktop-feedback/issues/116

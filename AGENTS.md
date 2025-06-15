## .cursorrules

Read .cursorrules before starting.

## Python testing, formatting and linting

If you've edited any python code, the following commands should run and not produce error codes. Fix any issues and re-run.

```
# Formatting 1:
uvx  ruff check --select I
# Formatting 2:
uvx ruff format --check .
# type checking: warnings in output are acceptable, but error codes are not
uv run pyright .
# tests:
uv run python3 -m pytest --benchmark-quiet -q .
```

## Web app testing, formatting and linting

If you change any web app code, the following commands should run and not produce error codes. Fix any issues and re-run.

```
# All commands below should be run from app/web_ui directory
cd app/web_ui
npm run format_check
npm run lint
npm run check
npm run test_run
npm run build > /dev/null
```

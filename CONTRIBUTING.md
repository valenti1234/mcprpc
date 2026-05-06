# Contributing

Thanks for contributing.

## Development setup

This is a monorepo. Each package/service has its own dependencies and test commands.

### Python packages

Create a virtual environment per package (recommended), then install in editable mode:

```bash
cd mr-router
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[test]"
pytest
```

Do the same for `mr-registry/`, `mc-gui/`, and `mc-automesh/`.

### Node package

```bash
cd mc-node-automesh
npm ci
npm test
```

## Pull requests

- Keep changes focused and include tests when you change behavior.
- Avoid committing generated artifacts (`__pycache__`, `*.egg-info`, DB files, `node_modules`).
- Prefer small, reviewable commits.


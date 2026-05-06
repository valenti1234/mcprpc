# Publishing

This repository is a monorepo. Each package is released independently.

## GitHub Actions release (recommended)

This repo includes a tag-driven release workflow:

- Python packages publish to PyPI

### Required secrets

No repository secrets are required if you use PyPI Trusted Publishing (OIDC).

Configure Trusted Publishing in PyPI for each project you want to publish:

- PyPI project → Publishing → Add a trusted publisher
- Select GitHub as the provider
- Repository: your org/user + repo name
- Workflow file: `.github/workflows/release.yml`
- Environment: optional (use if you want an approval gate)

### Tag formats

The workflow triggers on these tags and verifies that the tag version matches the package version:

- `mr-registry-vX.Y.Z` → publishes `mr-registry/` to PyPI
- `mr-router-vX.Y.Z` → publishes `mr-router/` to PyPI
- `mc-gui-vX.Y.Z` → publishes `mc-gui/` to PyPI
- `mc-automesh-vX.Y.Z` → publishes `mc-automesh/` to PyPI

## Python (PyPI)

Recommended steps for each Python package directory (`mr-registry/`, `mr-router/`, `mc-gui/`, `mc-automesh/`):

```bash
python3 -m pip install -U build twine
python3 -m build
python3 -m twine check dist/*
```

Then upload:

```bash
python3 -m twine upload dist/*
```

## Node (npm)

For `mc-node-automesh/` (package name: `mcprpc`):

```bash
cd mc-node-automesh
npm ci
npm run build
npm pack
```

Then publish:

```bash
npm publish
```

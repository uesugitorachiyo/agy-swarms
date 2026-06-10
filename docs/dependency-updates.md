# Dependency Updates

Dependency update automation lives in `.github/dependabot.yml`.

Dependabot checks for updates weekly and opens grouped pull requests for:

- GitHub Actions used by workflow files.
- Python dependencies managed by `uv` through `pyproject.toml` and `uv.lock`.

Each ecosystem is limited to five open pull requests and uses the `dependencies`
and `ci` labels. Dependabot branches still need the normal hosted merge gate:
review the diff, wait for required CI, and run local verification when the
dependency change affects packaging, release, or runtime behavior:

```bash
make verify
```

For Python dependency updates, keep `pyproject.toml` and `uv.lock` together in
the same pull request. For GitHub Actions updates, check the release notes for
permission, runtime, and cache behavior changes before merging.

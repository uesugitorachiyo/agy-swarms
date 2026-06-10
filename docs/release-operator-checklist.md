# Release Operator Checklist

Use this checklist when cutting a package release from `main`. Replace
`<version>` with the package version without the leading `v`, such as `0.5.4`.
Replace `<pr>` with the release-prep pull request number.

## 1. Prepare The Release Branch

- Start from a clean, current `main`:

```bash
git switch main
git pull --ff-only
git status --short
```

- Create a release-prep branch:

```bash
git switch -c release/<version>
```

## 2. Update Release Metadata

- Update `pyproject.toml` to `<version>`.
- Refresh `uv.lock` so the `agy-swarms` package entry matches:

```bash
uv lock
```

- Move relevant `CHANGELOG.md` bullets from `Unreleased` into a dated
  `v<version>` section.
- Update `docs/versioning.md` so the current package release and matching tag
  are `v<version>`.
- Confirm release artifacts will have these names:

```text
agy_swarms-<version>-py3-none-any.whl
agy_swarms-<version>.tar.gz
SHA256SUMS.txt
```

## 3. Verify Locally

Run the full local release gate:

```bash
make verify
```

Record the pytest count, mypy file count, and release health result for PR
verification evidence.

## 4. Open And Verify The Pull Request

Push the release-prep branch and open the pull request:

```bash
git push -u origin release/<version>
gh pr create --title "Prepare <version> release"
```

Wait for hosted checks:

```bash
gh pr checks <pr> --watch --interval 10
```

Update the PR verification section if needed:

```bash
PR_NUMBER=<pr> make pr-verification
```

Merge only after the required checks pass and branch protection requirements are
satisfied.

## 5. Tag The Release

After the release-prep PR lands on `main`, sync locally and create the annotated
tag:

```bash
git switch main
git pull --ff-only
git tag -a v<version> -m "v<version>"
git push origin v<version>
```

Confirm the tag points at the intended `main` commit:

```bash
git show --no-patch --oneline v<version>
```

## 6. Publish The GitHub Release

The release workflow runs automatically for pushed `v*` tags. If an operator
needs to rerun it for an existing tag, dispatch it manually:

```bash
gh workflow run release.yml -f tag=v<version>
```

Watch the run:

```bash
gh run list --workflow Release --limit 3
gh run watch <run-id> --interval 10
```

The workflow verifies `v<version>` against `pyproject.toml` with
`scripts/verify_release_tag.py` before it runs `make verify`, rebuilds
artifacts, or creates the GitHub Release.

Verify the published GitHub Release and attached artifacts:

```bash
gh release view v<version> --json tagName,name,isDraft,isPrerelease,url,assets
```

The release must be non-draft, non-prerelease unless intentionally marked
otherwise, and it must include both the wheel and source distribution.
It must also include `SHA256SUMS.txt`.

Verify the published assets and checksum manifest:

```bash
uv run python scripts/verify_release_assets.py --tag v<version> --repo uesugitorachiyo/agy-swarms
```

## 7. Capture Final Evidence

Record the final evidence in the release PR, changelog, or handoff note:

- Local `make verify` result.
- PR CI result.
- Post-merge `main` CI result.
- Release workflow result.
- GitHub Release URL.
- Wheel and source distribution asset names.
- `SHA256SUMS.txt` asset name and checksum verification result.

Leave the checkout clean:

```bash
git status --short
```

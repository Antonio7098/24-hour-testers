# Releasing Stageflow

This guide describes the workflow for publishing a new Stageflow release while keeping the
`pyproject.toml` version, git tags, and documentation in sync.

## Prerequisites

- You have push access to the repository and PyPI (if publishing artifacts).
- Your working tree is clean (`git status` shows no changes).
- You are on the default release branch (usually `main`).

## Release Checklist

1. **Update code and docs**
   - Finish the changes intended for the release.
   - Update `changelog.json` with a new entry at the top.
   - Ensure any user-facing docs reflect the changes (README, docs index, guides, etc.).

2. **Bump the project version**
   - Edit `[project].version` inside `pyproject.toml`.
   - Commit the change as part of your release PR.

3. **Verify version references**
   - Run `python3 scripts/check_version_sync.py`.
   - This script ensures:
     - `pyproject.toml` version is the source of truth.
     - `README.md` uses the same `Latest release: vX.Y.Z`.
     - `docs/index.md` highlights the same version in the “New in Stageflow …” callout.
     - `changelog.json`’s latest entry matches `vX.Y.Z`.
   - Fix any mismatches reported by the script.

4. **Merge the release PR**
   - The version checker runs in CI; the build must be green before merging.

5. **Tag the release**
   - From the default branch with a clean working tree, run:
     ```bash
     python3 scripts/release.py --push
     ```
   - The helper script will:
     - Re-run the version sync check.
     - Ensure the working tree is clean and the tag does not exist.
     - Create an annotated tag `vX.Y.Z`.
     - Push the tag to `origin` when `--push` is used.

6. **Publish artifacts (optional)**
   - If you distribute wheels/sdists, build and upload them after the tag is created.

## Dry-run mode

Use `python3 scripts/release.py --dry-run` to preview the commands without making changes. This
is useful while rehearsing the workflow or validating CI environments.

## Troubleshooting

- If the script reports mismatched versions, update the referenced file and rerun the checker.
- If a tag already exists, bump `pyproject.toml` to the next version before tagging again.
- Always ensure `git status` is clean; stash or commit local changes before starting the release.

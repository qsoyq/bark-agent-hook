# Release Notes

Use this directory for release process notes and release-specific follow-up.

The current release path is:

1. Merge reviewed changes to `main`.
2. Let CI validate the Python matrix and lint checks.
3. Create or reuse the stable `project.version` GitHub release.
4. Publish to PyPI through the protected `pypi` environment with trusted publishing.

Manual publishing requires an existing stable `x.y.z` release tag and verifies required CI checks for the release commit before publishing.

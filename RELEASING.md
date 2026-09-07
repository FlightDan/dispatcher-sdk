# Releasing

Publish developer previews on GitHub Releases. PyPI publishing is not configured.
The release workflow uses the repository's temporary GitHub token.

1. Update `pyproject.toml`, `src/dispatcher_sdk/_version.py`, the changelog and
   versioned install examples together. The package source-version declaration
   must agree with distribution metadata in a release artifact.
2. Run the test matrix and review the candidate. A local test run only verifies
   the Python/platform pair on which it ran.
3. Inspect the staged source and release artifacts for secrets and private data.
   The workflow runs Gitleaks against source; source archives must contain only
   the SDK, public docs, tests, examples and release metadata.
4. Push a tag matching the package version, for example `v0.6.0`.
   The workflow verifies that the tag and distribution version agree, then tests
   the tagged candidate, builds the source archive and wheel, generates
   `SHA256SUMS`, and publishes a GitHub prerelease.
5. Verify the release's artifacts and enable private vulnerability reporting.
   Fix any required job that fails before publishing, and verify the changed
   runtime code with a new test run.

For a manual first release, wait for CI on the exact committed candidate, build
and install its wheel outside the repository, run the documented examples, then
upload the source archive, wheel and checksums. A tag identifies the released
source. Subsequent changes require a new version; do not replace its artifacts.

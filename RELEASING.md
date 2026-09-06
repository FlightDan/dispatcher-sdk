# Releasing

Publish developer previews on GitHub Releases. PyPI publishing is not configured.
The release workflow uses the repository's temporary GitHub token.

1. Update `pyproject.toml`, the changelog and versioned install examples together.
2. Run the test matrix and review the candidate. Local checks alone do not
   establish that every supported Python/platform pair passed.
3. Inspect the staged source and release artifacts for secrets and private data.
   The workflow runs Gitleaks against source; source archives must contain only
   the SDK, public docs, tests, examples and release metadata.
4. Push a tag matching the package version, for example `v0.5.1`.
   The workflow verifies that the tag and distribution version agree, then tests
   the tagged candidate, builds the source archive and wheel, generates
   `SHA256SUMS`, and publishes a GitHub prerelease.
5. Verify the release's artifacts and enable private vulnerability reporting.
   If any required job fails, fix it before publishing. Do not relabel an old
   test report as evidence for changed runtime code.

For a manual first release, wait for CI on the exact committed candidate, build
and install its wheel outside the repository, run the documented examples, then
upload the source archive, wheel and checksums. A tag identifies the released
source; subsequent changes require a new version rather than replaced artifacts.

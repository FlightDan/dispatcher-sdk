# Releasing

Publish formal versions on GitHub Releases. PyPI publishing is not configured.
The workflow uses the repository's temporary GitHub token.

1. Update `pyproject.toml`, `src/dispatcher_sdk/_version.py`, version-related
   tests, documentation and `CHANGELOG.md` together. A formal version such as
   `0.7.2` must agree with its wheel metadata and source distribution.
2. Fix known defects, complete independent review and necessary local validation,
   then push the final candidate. Keep all sixteen platform/Python environments.
   Each executes the complete installed suite once, plus packaging, public/native
   acceptance, typing, docs, examples and six independent restart consumers.
3. Review the entire matrix's original logs, applicable skips and retained
   evidence. The Ubuntu x64 Python 3.12 packaging harness exports its actual
   sdist and rebuilt, installed wheel only after its assertions succeed. CI
   retains them as `release-packages-RUN_ID-RUN_ATTEMPT`; do not rebuild them for
   publication. The source archive follows `MANIFEST.in` and contains public
   SDK source, docs, tests, examples and historical provenance metadata.
4. Integrate the validated commit into `main`, preferably by a fast
   forward. Preserve existing branches/tags and use no force push. CI admission
   reuses a previous same-commit run only when its latest attempt has all sixteen
   matrix jobs and the history scan successful, and its original package artifact
   is available. Skipped or partial attempts cannot qualify. An API error fails
   visibly. Internal PRs use their existing push CI; forks validate their merge.
5. Push the version tag (for example, `v0.7.2`) at that validated commit. The
   release workflow requires the
   matching formal version, the complete original CI and its immutable artifact
   ID. It downloads and checks package version metadata, then publishes the
   original wheel and sdist as a formal Latest Release. It does not run another
   matrix, rebuild packages, generate checksums or publish to PyPI.
6. Re-read the Release, its assets and the default branch. Set `main`
   as GitHub's default only under the applicable release authorization. Record
   final raw evidence in the acceptance index. Post-publication ledger-only
   changes receive documentation validation; a different Git commit does not
   qualify for a new release tag using the prior commit's package artifact.

Artifact names include their run attempt, preserving earlier attempts. Missing,
expired or partial acceptance blocks publication. Do not replace a published
version's assets; changed release content needs corresponding validation and a
new release version. Manual publication must use the same original tested
packages and preserve the original CI/evidence links.

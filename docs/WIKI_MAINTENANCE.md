# Maintaining the Wiki and agent documentation

The [bilingual Wiki sources](../wiki/Home.md) contain navigation and short user
guides. [DocsforAgents](../DocsforAgents/README.md) helps coding agents find the
English integration documentation. Keep detailed API contracts in `docs/`.
Update those contracts and runnable examples first, then update both Wiki
language editions and the agent summaries in the same change.

## Check and export

After installing the current checkout, run:

```sh
python scripts/check_docs.py
python scripts/export_wiki.py --output /tmp/dispatcher-wiki-preview --ref main
```

The output directory must be new or empty and outside the source checkout. On
Windows, substitute a suitable temporary directory. The exporter preserves page
filenames, converts local Wiki links to GitHub Wiki page names, and converts
repository links to GitHub blob URLs. It makes no network requests, commits or
pushes. It checks that local target files exist, but cannot verify remote availability.

For publication, use a published commit SHA where possible, rather than `main`.
The referenced commit must contain the matching code, `docs/`, `DocsforAgents/`
and examples. Do not publish links to an unpushed checkout or unreleased APIs
absent from the referenced revision. The `--ref main` preview option does not
check whether the current files are on `main`.

## Publish to GitHub Wiki

GitHub Wiki uses a separate Git repository. If it has no initial page, create
`Home` through the repository's Wiki tab first. GitHub documents this initial
page requirement in [Adding or editing wiki pages](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).

After the matching SDK documentation revision is published:

1. Export again with that published commit SHA into a fresh directory.
2. Clone `https://github.com/FlightDan/dispatcher-sdk.wiki.git` into a separate
   directory, or pull its current default branch if already cloned.
3. Copy the exported Markdown files into that Wiki checkout. Review its diff;
   preserve any unrelated Wiki pages. `_Sidebar.md` provides both languages.
4. Commit the reviewed page changes and push the Wiki's default branch.
5. Open `Home`, switch language, and check a sidebar link, an API link and the
   DocsforAgents link in GitHub.

Maintain content in this repository's `wiki/` directory. If a page is edited
through GitHub, reconcile it back here before the next export. Renamed or removed
pages need to be cleaned up in the Wiki repository; the exporter does not delete
published pages. Publishing the GitHub Wiki does not release an SDK package.
